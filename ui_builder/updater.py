"""Self-update from GitHub.

Checks the version in `<repo>/<branch>/ui_builder/__init__.py` and, on request,
downloads the branch archive and replaces the installed addon files in place.
Network work happens on a background thread; the UI polls `STATE`.
"""

import io
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

import bpy

DEFAULT_REPO = "11moo11/Blender-UI-Builder"
DEFAULT_BRANCH = "main"
SOURCE_FOLDER = "ui_builder"  # folder inside the repo that holds the addon package

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_ZIP_BYTES = 25 * 1024 * 1024
ALLOWED_EXT = {".py", ".md", ".txt", ".toml", ".json", ".cfg"}
_VERSION_RE = re.compile(r"[\"']version[\"']\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


class State:
    IDLE, CHECKING, UP_TO_DATE, AVAILABLE, INSTALLING, INSTALLED, ERROR = (
        "IDLE", "CHECKING", "UP_TO_DATE", "AVAILABLE", "INSTALLING", "INSTALLED", "ERROR")

    def __init__(self):
        self.status = self.IDLE
        self.message = ""
        self.remote_version = None
        self._lock = threading.Lock()

    def set(self, status, message="", remote_version=None):
        with self._lock:
            self.status = status
            self.message = message
            if remote_version is not None:
                self.remote_version = remote_version

    @property
    def busy(self):
        return self.status in (self.CHECKING, self.INSTALLING)


STATE = State()


def local_version():
    mod = sys.modules.get(__package__)
    return tuple(getattr(mod, "bl_info", {}).get("version", (0, 0, 0)))


def fmt_version(v):
    return ".".join(str(x) for x in v) if v else "?"


def online_allowed():
    return getattr(bpy.app, "online_access", True)


def _validate(repo, branch):
    if not _REPO_RE.match(repo or ""):
        raise ValueError("Repository must look like 'owner/name'")
    if not _BRANCH_RE.match(branch or "") or ".." in branch:
        raise ValueError("Invalid branch name")


def _download(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "blender-ui-builder-updater"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download is larger than expected; aborting")
    return data


def fetch_remote_version(repo, branch):
    _validate(repo, branch)
    url = "https://raw.githubusercontent.com/%s/%s/%s/__init__.py" % (repo, branch, SOURCE_FOLDER)
    text = _download(url, 512 * 1024).decode("utf-8", "replace")
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError("Could not read a version from the repository")
    return tuple(int(x) for x in m.groups())


def _extract(data, dest):
    """Extract only `<root>/ui_builder/**` from a GitHub archive into dest. Returns file count."""
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")
            if len(parts) < 3 or parts[1] != SOURCE_FOLDER:
                continue
            rel = parts[2:]
            if any(p in ("", ".", "..") or "\\" in p or ":" in p for p in rel):
                continue
            if "__pycache__" in rel or os.path.splitext(rel[-1])[1].lower() not in ALLOWED_EXT:
                continue
            target = os.path.join(dest, *rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            count += 1
    return count


def _managed_files(root):
    found = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            found.add(os.path.relpath(os.path.join(base, f), root))
    return found


def install_from_github(repo, branch):
    """Download and apply the update. Raises on failure (installed files are rolled back)."""
    _validate(repo, branch)
    url = "https://github.com/%s/archive/refs/heads/%s.zip" % (repo, branch)
    data = _download(url, MAX_ZIP_BYTES)
    work = tempfile.mkdtemp(prefix="uib_update_")
    try:
        new_dir = os.path.join(work, "new")
        os.makedirs(new_dir)
        if _extract(data, new_dir) == 0:
            raise ValueError("Archive has no '%s' folder" % SOURCE_FOLDER)
        init = os.path.join(new_dir, "__init__.py")
        if not os.path.isfile(init):
            raise ValueError("Archive is missing __init__.py")
        with open(init, encoding="utf-8") as f:
            if not _VERSION_RE.search(f.read()):
                raise ValueError("Downloaded addon has no version; aborting")
        backup = os.path.join(work, "backup")
        shutil.copytree(ADDON_DIR, backup, ignore=shutil.ignore_patterns("__pycache__"))
        try:
            for rel in _managed_files(ADDON_DIR) - _managed_files(new_dir):
                os.remove(os.path.join(ADDON_DIR, rel))
            for rel in _managed_files(new_dir):
                target = os.path.join(ADDON_DIR, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(os.path.join(new_dir, rel), target)
        except Exception:
            for rel in _managed_files(backup):
                target = os.path.join(ADDON_DIR, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(os.path.join(backup, rel), target)
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _redraw():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


def _watch():
    """Timer: redraw while a background job is running, then once more when done."""
    _redraw()
    return 0.5 if STATE.busy else None


def _start(target):
    threading.Thread(target=target, daemon=True).start()
    bpy.app.timers.register(_watch, first_interval=0.3)


def check_async(repo, branch):
    if STATE.busy:
        return
    if not online_allowed():
        STATE.set(State.ERROR, "Online access is disabled in Blender (Preferences > System > Network).")
        return
    STATE.set(State.CHECKING, "Checking GitHub...")

    def job():
        try:
            remote = fetch_remote_version(repo, branch)
            if remote > local_version():
                STATE.set(State.AVAILABLE, "Version %s is available." % fmt_version(remote), remote)
            else:
                STATE.set(State.UP_TO_DATE, "You have the latest version.", remote)
        except urllib.error.HTTPError as e:
            STATE.set(State.ERROR, "GitHub returned %s. Check the repository and branch." % e.code)
        except Exception as e:
            STATE.set(State.ERROR, "Update check failed: %s" % e)

    _start(job)


def install_async(repo, branch):
    if STATE.busy:
        return
    if not online_allowed():
        STATE.set(State.ERROR, "Online access is disabled in Blender (Preferences > System > Network).")
        return
    STATE.set(State.INSTALLING, "Downloading update...")

    def job():
        try:
            install_from_github(repo, branch)
            STATE.set(State.INSTALLED, "Updated. Reload scripts or restart Blender to finish.")
        except urllib.error.HTTPError as e:
            STATE.set(State.ERROR, "GitHub returned %s. Check the repository and branch." % e.code)
        except Exception as e:
            STATE.set(State.ERROR, "Update failed: %s" % e)

    _start(job)


def reload_scripts():
    """Reload all addons (picks up the freshly written files)."""
    def run():
        bpy.ops.script.reload()
        return None
    bpy.app.timers.register(run, first_interval=0.2)
