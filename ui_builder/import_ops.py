"""Operators for importing another addon's panels."""

import sys

import bpy

from . import elements as el
from . import importer
from .operators import new_element
from .properties import ensure_mock_items, settings
from . import tree


def _location(cls):
    return el.Place(getattr(cls, "bl_space_type", ""), getattr(cls, "bl_region_type", ""),
                    getattr(cls, "bl_context", "") or None, getattr(cls, "bl_category", ""),
                    getattr(cls, "bl_parent_id", "")).title()


class UIB_OT_toggle_import_panel(bpy.types.Operator):
    """Include or exclude this panel from the import"""
    bl_idname = "ui_builder.toggle_import_panel"
    bl_label = "Toggle Panel"
    bl_options = {"INTERNAL"}

    idname: bpy.props.StringProperty()

    def execute(self, context):
        s = settings(context)
        for i, p in enumerate(s.import_skip):
            if p.idname == self.idname:
                s.import_skip.remove(i)
                return {"FINISHED"}
        s.import_skip.add().idname = self.idname
        return {"FINISHED"}


def panel_id(cls):
    return getattr(cls, "bl_idname", "") or cls.__name__


def listed_panels(s):
    """(kind, class, included) for everything the chosen addon draws: panels, headers, menus, dialogs, prefs."""
    skipped = {p.idname for p in s.import_skip}
    return [(kind, c, panel_id(c) not in skipped) for kind, c in importer.addon_ui(s.import_module)]


class UIB_OT_import_addon(bpy.types.Operator):
    """Copy the ticked UI (panels, headers, menus, dialogs, preferences) of the addon into the builder"""
    bl_idname = "ui_builder.import_addon"
    bl_label = "Import Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return settings(context).import_module not in ("", "NONE")

    def execute(self, context):
        s = settings(context)
        module = s.import_module
        chosen = [(kind, c) for kind, c, included in listed_panels(s) if included]
        if not chosen:
            self.report({"WARNING"}, "Nothing selected")
            return {"CANCELLED"}

        ctx = importer.Ctx(context)
        items, partial = {}, []
        for kind, cls in chosen:
            item, error = importer.build_panel(cls, ctx, kind, explore=s.import_explore, hidden=s.import_hidden, module=module)
            items[panel_id(cls)] = item
            if error:
                partial.append("%s (%s)" % (item.label, error))
        roots = []
        for kind, cls in chosen:
            parent = items.get(getattr(cls, "bl_parent_id", "")) if kind == "PANEL" else None
            (parent.children if parent else roots).append(items[panel_id(cls)])

        placed = [c for kind, c in chosen if kind in ("PANEL", "HEADER") and getattr(c, "bl_space_type", "")]
        if s.import_mode == "REPLACE":
            s.elements.clear()
            mod = sys.modules.get(module)
            info = getattr(mod, "bl_info", None) or {}
            s.addon_name = importer.addon_display_name(module)
            if info.get("author"):
                s.author = str(info["author"])
            s.prefix = el.slugify(module.split(".")[-1], "my_addon")
            first = placed[0] if placed else None
            if first is not None:
                key = (getattr(first, "bl_space_type", ""), getattr(first, "bl_region_type", ""),
                       getattr(first, "bl_context", "") or None)
                for pid, spec in el.PLACEMENTS.items():
                    if spec[1:] == key:
                        s.placement = pid
                        break
                if getattr(first, "bl_category", ""):
                    s.category = first.bl_category
        project = el.project_place(s)
        for kind, cls in chosen:
            if kind in ("PANEL", "HEADER") and not (kind == "PANEL" and getattr(cls, "bl_parent_id", "") in items):
                items[panel_id(cls)].fields.update(importer.placement_fields(cls, project))
        importer.commit(s, roots, new_element, tree.normalize)
        s.active_index = 0
        ensure_mock_items(context.scene)
        self.report({"INFO"}, "Imported %d item(s), %d element(s)" % (len(chosen), len(s.elements)))
        if partial:
            self.report({"WARNING"}, "Partly imported (draw code needs context that isn't "
                                     "available, e.g. a selected object): " + "; ".join(partial))
        return {"FINISHED"}


classes = (UIB_OT_toggle_import_panel, UIB_OT_import_addon)
