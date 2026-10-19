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


class UIB_OT_scan_addon(bpy.types.Operator):
    """List the panels the chosen addon has registered"""
    bl_idname = "ui_builder.scan_addon"
    bl_label = "Scan Panels"

    @classmethod
    def poll(cls, context):
        return settings(context).import_module not in ("", "NONE")

    def execute(self, context):
        s = settings(context)
        s.import_panels.clear()
        classes = importer.addon_panels(s.import_module)
        for cls in classes:
            row = s.import_panels.add()
            row.idname = getattr(cls, "bl_idname", "") or cls.__name__
            row.label = getattr(cls, "bl_label", "") or cls.__name__
            row.parent_id = getattr(cls, "bl_parent_id", "")
            row.location = _location(cls)
        if not classes:
            self.report({"WARNING"}, "That addon has no registered panels")
        return {"FINISHED"}


class UIB_OT_import_addon(bpy.types.Operator):
    """Copy the selected panels of the addon into the builder"""
    bl_idname = "ui_builder.import_addon"
    bl_label = "Import Selected Panels"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return settings(context).import_module not in ("", "NONE")

    def execute(self, context):
        s = settings(context)
        module = s.import_module
        if not len(s.import_panels):
            bpy.ops.ui_builder.scan_addon()
        wanted = {p.idname for p in s.import_panels if p.include}
        classes = [c for c in importer.addon_panels(module)
                   if (getattr(c, "bl_idname", "") or c.__name__) in wanted]
        if not classes:
            self.report({"WARNING"}, "No panels selected")
            return {"CANCELLED"}

        ctx = importer.Ctx(context)
        items, partial = {}, []
        for cls in classes:
            item, error = importer.build_panel(cls, ctx)
            items[getattr(cls, "bl_idname", "") or cls.__name__] = item
            if error:
                partial.append("%s (%s)" % (item.label, error))
        roots = []
        for cls in classes:
            idname = getattr(cls, "bl_idname", "") or cls.__name__
            parent = items.get(getattr(cls, "bl_parent_id", ""))
            (parent.children if parent else roots).append(items[idname])

        if s.import_mode == "REPLACE":
            s.elements.clear()
            first = classes[0]
            mod = sys.modules.get(module)
            info = getattr(mod, "bl_info", None) or {}
            s.addon_name = importer.addon_display_name(module)
            if info.get("author"):
                s.author = str(info["author"])
            s.prefix = el.slugify(module.split(".")[-1], "my_addon")
            key = (getattr(first, "bl_space_type", ""), getattr(first, "bl_region_type", ""),
                   getattr(first, "bl_context", "") or None)
            for pid, spec in el.PLACEMENTS.items():
                if spec[1:] == key:
                    s.placement = pid
                    break
            if getattr(first, "bl_category", ""):
                s.category = first.bl_category
        project = el.project_place(s)
        for cls in classes:
            parent_in_addon = getattr(cls, "bl_parent_id", "") in items
            if not parent_in_addon:
                items[getattr(cls, "bl_idname", "") or cls.__name__].fields.update(
                    importer.placement_fields(cls, project))
        importer.commit(s, roots, new_element, tree.normalize)
        s.active_index = 0
        ensure_mock_items(context.scene)
        self.report({"INFO"}, "Imported %d panel(s), %d element(s)" % (len(classes), len(s.elements)))
        if partial:
            self.report({"WARNING"}, "Partly imported (draw code needs context that isn't "
                                     "available, e.g. a selected object): " + "; ".join(partial))
        return {"FINISHED"}


classes = (UIB_OT_scan_addon, UIB_OT_import_addon)
