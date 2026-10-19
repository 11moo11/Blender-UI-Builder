"""Addon preferences, including the GitHub updater controls."""

import bpy
from bpy.props import BoolProperty, StringProperty

from . import updater


class UIB_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    repo: StringProperty(name="GitHub Repository", default=updater.DEFAULT_REPO,
                         description="owner/name of the repository to update from")
    branch: StringProperty(name="Branch", default=updater.DEFAULT_BRANCH,
                           description="Falls back to the repository's default branch if this one does not exist")
    token: StringProperty(name="Access Token", subtype="PASSWORD",
                          description="Only needed for private repositories: a GitHub token with read access to "
                                      "repository contents. Stored in your Blender preferences")
    auto_check: BoolProperty(name="Check for updates on startup", default=True)

    def draw(self, context):
        draw_update_box(self.layout, self)


def get_prefs(context=None):
    addon = (context or bpy.context).preferences.addons.get(__package__)
    return addon.preferences if addon else None


def draw_update_box(layout, prefs, compact=False):
    st = updater.STATE
    box = layout.box()
    box.label(text="Updates (GitHub)", icon="URL")
    box.label(text="Installed version: %s" % updater.fmt_version(updater.local_version()))
    if not compact:
        col = box.column()
        col.prop(prefs, "repo")
        col.prop(prefs, "branch")
        col.prop(prefs, "token")
        col.prop(prefs, "auto_check")
    if st.message:
        icon = {"ERROR": "ERROR", "AVAILABLE": "INFO", "INSTALLED": "CHECKMARK",
                "UP_TO_DATE": "CHECKMARK"}.get(st.status, "TIME")
        box.label(text=st.message, icon=icon)
    row = box.row(align=True)
    sub = row.row(align=True)
    sub.enabled = not st.busy
    sub.operator("ui_builder.check_update", icon="FILE_REFRESH")
    sub = row.row(align=True)
    sub.enabled = st.status == st.AVAILABLE
    sub.alert = st.status == st.AVAILABLE
    sub.operator("ui_builder.install_update", icon="IMPORT",
                 text="Install %s" % updater.fmt_version(st.remote_version)
                 if st.status == st.AVAILABLE else "Update Now")
    if st.status == st.INSTALLED:
        box.operator("ui_builder.restart_blender", icon="QUIT")


class UIB_OT_check_update(bpy.types.Operator):
    """Look on GitHub for a newer version of this addon"""
    bl_idname = "ui_builder.check_update"
    bl_label = "Check for Updates"

    def execute(self, context):
        p = get_prefs(context)
        updater.check_async(p.repo if p else updater.DEFAULT_REPO, p.branch if p else updater.DEFAULT_BRANCH,
                            p.token if p else "")
        return {"FINISHED"}


class UIB_OT_install_update(bpy.types.Operator):
    """Download the latest version from GitHub and replace the installed files"""
    bl_idname = "ui_builder.install_update"
    bl_label = "Update Now"

    @classmethod
    def poll(cls, context):
        return updater.STATE.status == updater.State.AVAILABLE

    def invoke(self, context, event):
        p = get_prefs(context)
        return context.window_manager.invoke_confirm(
            self, event, message="Download and install the latest code from %s (%s)?" % (
                p.repo if p else updater.DEFAULT_REPO, p.branch if p else updater.DEFAULT_BRANCH))

    def execute(self, context):
        p = get_prefs(context)
        repo = p.repo if p else updater.DEFAULT_REPO
        branch = p.branch if p else updater.DEFAULT_BRANCH
        updater.install_async(repo, branch, p.token if p else "")
        return {"FINISHED"}


class UIB_OT_restart_blender(bpy.types.Operator):
    """Restart Blender so the updated addon loads cleanly"""
    bl_idname = "ui_builder.restart_blender"
    bl_label = "Restart Blender"

    save_first: BoolProperty(name="Save the file first", default=True,
                             description="Save the current .blend before restarting (only if it already has a name)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Blender will close and reopen.")
        if bpy.data.filepath:
            col.prop(self, "save_first")
            if not self.save_first and bpy.data.is_dirty:
                col.label(text="Unsaved changes will be lost.", icon="ERROR")
        else:
            col.label(text="This file has never been saved; it will be lost.", icon="ERROR")

    def execute(self, context):
        import subprocess
        import sys
        if bpy.data.filepath and self.save_first:
            bpy.ops.wm.save_mainfile()
        cmd = [bpy.app.binary_path]
        if bpy.data.filepath:
            cmd.append(bpy.data.filepath)
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            self.report({"ERROR"}, "Could not start Blender: %s. Please restart it manually." % e)
            return {"CANCELLED"}
        bpy.ops.wm.quit_blender()
        return {"FINISHED"}


def _startup_check():
    p = get_prefs()
    if p and p.auto_check and updater.online_allowed():
        updater.check_async(p.repo, p.branch, p.token)
    return None


classes = (UIB_Preferences, UIB_OT_check_update, UIB_OT_install_update, UIB_OT_restart_blender)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.timers.register(_startup_check, first_interval=5.0)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
