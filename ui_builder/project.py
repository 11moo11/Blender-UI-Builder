"""Export / import operators and the bundled example."""

import os

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import branches, export, tree
from .operators import new_element
from .properties import ensure_mock_items, settings


def _show_text(context, text):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "TEXT_EDITOR":
                area.spaces.active.text = text
                area.tag_redraw()
                return


class UIB_OT_export(bpy.types.Operator):
    """Generate code from the current UI"""
    bl_idname = "ui_builder.export"
    bl_label = "Export"

    format: EnumProperty(items=[("PYTHON", "Python Addon", ""), ("LLM", "LLM Prompt", ""), ("JSON", "JSON Layout", "")],
                         options={"SKIP_SAVE"})
    target: EnumProperty(items=[("TEXT", "Text Editor", ""), ("CLIPBOARD", "Clipboard", ""), ("FILE", "File", "")],
                         default="TEXT", options={"SKIP_SAVE"})
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
    filter_glob: StringProperty(default="*.py;*.md;*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return len(settings(context).elements) > 0

    def _exporter(self, context):
        s = settings(context)
        return s, export.Exporter(s)

    def invoke(self, context, event):
        if self.target == "FILE":
            s, ex = self._exporter(context)
            fmt = self.format or s.export_format
            self.filepath = os.path.join(os.path.dirname(bpy.data.filepath) if bpy.data.filepath else "", ex.filename(fmt))
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def execute(self, context):
        s, ex = self._exporter(context)
        fmt = self.format or s.export_format
        try:
            text = ex.text(fmt)
        except Exception as e:
            self.report({"ERROR"}, "Export failed: %s" % e)
            return {"CANCELLED"}
        name = ex.filename(fmt)
        if self.target == "CLIPBOARD":
            context.window_manager.clipboard = text
            self.report({"INFO"}, "Copied %d lines to the clipboard" % (text.count("\n") + 1))
        elif self.target == "FILE":
            path = bpy.path.abspath(self.filepath)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.report({"INFO"}, "Saved %s" % path)
        else:
            block = bpy.data.texts.get(name) or bpy.data.texts.new(name)
            block.clear()
            block.write(text)
            _show_text(context, block)
            self.report({"INFO"}, "Written to text block '%s' (open the Text Editor to see it)" % block.name)
        return {"FINISHED"}


class UIB_OT_import_json(bpy.types.Operator, ImportHelper):
    """Load a UI Builder JSON layout (replaces the current project)"""
    bl_idname = "ui_builder.import_json"
    bl_label = "Import JSON Layout"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8") as f:
                export.load_project(settings(context), f.read())
        except Exception as e:
            self.report({"ERROR"}, "Could not import: %s" % e)
            return {"CANCELLED"}
        ensure_mock_items(context.scene)
        return {"FINISHED"}


# (type, label, indent, {property: value})
_EXAMPLE = [
    ("PANEL", "Render Helper", 0, {}),
    ("LABEL", "Quick render setup", 1, {"icon": "RENDER_STILL"}),
    ("ROW", "Row", 1, {"align": True}),
    ("BUTTON", "Render Still", 2, {"icon": "RENDER_STILL"}),
    ("BUTTON", "Render Animation", 2, {"icon": "RENDER_ANIMATION"}),
    ("SEPARATOR", "Separator", 1, {}),
    ("ENUM", "Quality", 1, {"enum_items": "Draft, Medium, Final", "enum_style": "EXPAND"}),
    ("SLIDER", "Resolution Scale", 1, {}),
    ("BOOL", "Open when finished", 1, {"bool_value": True}),
    ("PANEL", "Output", 1, {"default_closed": True}),
    ("DIRPATH", "Output Folder", 2, {}),
    ("STRING", "File Name", 2, {"string_value": "render"}),
    ("COLOR", "Background", 2, {}),
    ("PANEL", "Layers", 0, {}),
    ("LIST", "Layer List", 1, {}),
    ("ROW", "Row", 1, {}),
    ("BUTTON", "Add", 2, {"icon": "ADD"}),
    ("BUTTON", "Remove", 2, {"icon": "REMOVE"}),
    ("PROGRESS", "Progress", 1, {"progress_factor": 0.4}),
]


def load_example(context):
    s = settings(context)
    s.elements.clear()
    with branches.no_sync():
        for type_id, label, indent, values in _EXAMPLE:
            new_element(s, type_id, len(s.elements), indent, label)
            e = s.elements[len(s.elements) - 1]
            for k, v in values.items():
                setattr(e, k, v)
    tree.normalize(s.elements)
    branches.sync_all(s)
    # show the Choice branching: something that only appears for the "Final" option
    for i, e in enumerate(s.elements):
        if e.option_id == "final":
            new_element(s, "LABEL", i + 1, e.indent + 1, "Final renders can take a long time")
            s.elements[i + 1].icon = "TIME"
            break
    s.active_index = 0
    s.addon_name = "Render Helper"
    s.prefix = "render_helper"
    s.category = "Render Helper"
    ensure_mock_items(context.scene)


class UIB_OT_load_example(bpy.types.Operator):
    """Replace the project with a small example UI"""
    bl_idname = "ui_builder.load_example"
    bl_label = "Load Example"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if len(settings(context).elements):
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        load_example(context)
        return {"FINISHED"}


classes = (UIB_OT_export, UIB_OT_import_json, UIB_OT_load_example)
