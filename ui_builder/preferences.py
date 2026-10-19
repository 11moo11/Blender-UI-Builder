"""Addon preferences, including the GitHub updater controls."""

import bpy
from bpy.props import BoolProperty, StringProperty

from . import updater


class UIB_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    repo: StringProperty(name="GitHub Repository", default=updater.DEFAULT_REPO,
                         description="owner/name of the repository to update from")
    branch: StringProperty(name="Branch", default=updater.DEFAULT_BRANCH)
    auto_check: BoolProperty(name="Check for updates on startup", default=True)
    auto_reload: BoolProperty(name="Reload scripts after updating", default=True,
                              description="Run Reload Scripts automatically once an update is installed")

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
        col.prop(prefs, "auto_check")
        col.prop(prefs, "auto_reload")
    if st.message:
        icon = {"ERROR": "ERROR", "AVAILABLE": "INFO", "INSTALLED": "CHECKMARK",
                "UP_TO_DATE": "CHECKMARK"}.get(st.status, "TIME")
        box.label(text=st.message, icon=icon)
    row = box.row(align=True)
    row.enabled = not st.busy
    row.operator("ui_builder.check_update", icon="FILE_REFRESH")
    sub = row.row(align=True)
    sub.alert = st.status == st.AVAILABLE
    sub.operator("ui_builder.install_update", icon="IMPORT",
                 text="Install %s" % updater.fmt_version(st.remote_version)
                 if st.status == st.AVAILABLE else "Update Now")
    if st.status == st.INSTALLED:
        box.operator("ui_builder.reload_scripts", icon="FILE_REFRESH")


class UIB_OT_check_update(bpy.types.Operator):
    """Look on GitHub for a newer version of this addon"""
    bl_idname = "ui_builder.check_update"
    bl_label = "Check for Updates"

    def execute(self, context):
        p = get_prefs(context)
        updater.check_async(p.repo if p else updater.DEFAULT_REPO, p.branch if p else updater.DEFAULT_BRANCH)
        return {"FINISHED"}


class UIB_OT_install_update(bpy.types.Operator):
    """Download the latest version from GitHub and replace the installed files"""
    bl_idname = "ui_builder.install_update"
    bl_label = "Update Now"

    def invoke(self, context, event):
        p = get_prefs(context)
        return context.window_manager.invoke_confirm(
            self, event, message="Download and install the latest code from %s (%s)?" % (
                p.repo if p else updater.DEFAULT_REPO, p.branch if p else updater.DEFAULT_BRANCH))

    def execute(self, context):
        p = get_prefs(context)
        repo = p.repo if p else updater.DEFAULT_REPO
        branch = p.branch if p else updater.DEFAULT_BRANCH
        updater.install_async(repo, branch)
        if p and p.auto_reload:
            bpy.app.timers.register(_reload_when_done, first_interval=1.0)
        return {"FINISHED"}


def _reload_when_done():
    st = updater.STATE
    if st.busy:
        return 0.5
    if st.status == st.INSTALLED:
        updater.reload_scripts()
    return None


class UIB_OT_reload_scripts(bpy.types.Operator):
    """Reload all addons so the updated code takes effect"""
    bl_idname = "ui_builder.reload_scripts"
    bl_label = "Reload Scripts"

    def execute(self, context):
        updater.reload_scripts()
        return {"FINISHED"}


def _startup_check():
    p = get_prefs()
    if p and p.auto_check and updater.online_allowed():
        updater.check_async(p.repo, p.branch)
    return None


classes = (UIB_Preferences, UIB_OT_check_update, UIB_OT_install_update, UIB_OT_reload_scripts)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.timers.register(_startup_check, first_interval=5.0)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
