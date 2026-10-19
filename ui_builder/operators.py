"""Operators that edit the element list."""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import elements as el
from . import icons, tree
from .properties import ensure_mock_items, settings

_ADD_ITEMS = [(d.id, d.label, d.help) for d in el._DEFS] + [("SUBPANEL", "Sub-panel", "Panel nested in the active panel")]


def _block_start_panel(elems, i):
    """Index of the nearest PANEL at or above element i (including ancestors), or -1."""
    indent = elems[i].indent
    while i >= 0:
        if elems[i].type == "PANEL" and elems[i].indent <= indent:
            return i
        if elems[i].indent < indent:
            indent = elems[i].indent
        i -= 1
    return -1


def new_element(s, type_id, index, indent, label=None):
    """Insert a fresh element at `index` with the given indent and return it."""
    d = el.DEFS[type_id]
    e = s.elements.add()
    e.type = type_id
    e.indent = indent
    e.label = label if label is not None else d.label
    if not e.ident:
        e.ident = el.slugify(e.label, el.slugify(type_id))
    s.elements.move(len(s.elements) - 1, index)
    if type_id == "LIST":
        ensure_mock_items(bpy.context.scene)
    return s.elements[index]  # `e` may be stale after the move


def _insert_position(s, type_id, nest):
    elems = s.elements
    i = s.active_index
    if not (0 <= i < len(elems)):
        return len(elems), 0
    active = elems[i]
    if type_id == "PANEL":
        if nest and active.type == "PANEL":
            return tree.block_end(elems, i), active.indent + 1
        p = _block_start_panel(elems, i)
        if p >= 0:
            return tree.block_end(elems, p), elems[p].indent
        return len(elems), 0
    if el.DEFS[active.type].container:
        return tree.block_end(elems, i), active.indent + 1
    return i + 1, active.indent


class UIB_OT_add(bpy.types.Operator):
    """Add an element (inside the active container, or after the active element)"""
    bl_idname = "ui_builder.add"
    bl_label = "Add Element"
    bl_options = {"REGISTER", "UNDO"}

    type: EnumProperty(items=_ADD_ITEMS)

    def execute(self, context):
        s = settings(context)
        type_id = "PANEL" if self.type == "SUBPANEL" else self.type
        nest = self.type == "SUBPANEL"
        if nest and not (0 <= s.active_index < len(s.elements) and s.elements[s.active_index].type == "PANEL"):
            self.report({"WARNING"}, "Select a panel first to add a sub-panel to it")
            return {"CANCELLED"}
        index, indent = _insert_position(s, type_id, nest)
        label = "Sub-panel" if nest else None
        new_element(s, type_id, index, indent, label)
        s.active_index = index
        tree.normalize(s.elements)
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_remove(bpy.types.Operator):
    """Remove the active element and everything inside it"""
    bl_idname = "ui_builder.remove"
    bl_label = "Remove Element"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        s = settings(context)
        return 0 <= s.active_index < len(s.elements)

    def execute(self, context):
        s = settings(context)
        i = s.active_index
        end = tree.block_end(s.elements, i)
        for _ in range(end - i):
            s.elements.remove(i)
        s.active_index = max(0, min(i, len(s.elements)) - 1) if len(s.elements) else 0
        _redraw(context)
        return {"FINISHED"}


def _copy_props(src, dst):
    for p in src.bl_rna.properties:
        if p.identifier == "rna_type" or p.is_readonly:
            continue
        try:
            setattr(dst, p.identifier, getattr(src, p.identifier))
        except (AttributeError, TypeError, ValueError):
            pass


class UIB_OT_duplicate(bpy.types.Operator):
    """Duplicate the active element and everything inside it"""
    bl_idname = "ui_builder.duplicate"
    bl_label = "Duplicate Element"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return UIB_OT_remove.poll(context)

    def execute(self, context):
        s = settings(context)
        i = s.active_index
        end = tree.block_end(s.elements, i)
        n = end - i
        for k in range(n):
            s.elements.add()  # may reallocate, so look elements up by index afterwards
            _copy_props(s.elements[i + k], s.elements[len(s.elements) - 1])
            s.elements.move(len(s.elements) - 1, end + k)
        s.active_index = end
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_move(bpy.types.Operator):
    """Move the active element (with its children) among its siblings"""
    bl_idname = "ui_builder.move"
    bl_label = "Move Element"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    @classmethod
    def poll(cls, context):
        return UIB_OT_remove.poll(context)

    def execute(self, context):
        s = settings(context)
        elems = s.elements
        a = s.active_index
        b = tree.block_end(elems, a)
        indent = elems[a].indent
        if self.direction == "UP":
            p = a - 1
            while p >= 0 and elems[p].indent > indent:
                p -= 1
            if p < 0 or elems[p].indent < indent:
                return {"CANCELLED"}
            for k in range(b - a):
                elems.move(a + k, p + k)
            s.active_index = p
        else:
            if b >= len(elems) or elems[b].indent < indent:
                return {"CANCELLED"}
            c = tree.block_end(elems, b)
            for k in range(c - b):
                elems.move(b + k, a + k)
            s.active_index = a + (c - b)
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_indent(bpy.types.Operator):
    """Move the active element into the container above it, or back out of its container"""
    bl_idname = "ui_builder.indent"
    bl_label = "Change Nesting"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("IN", "Into container above", ""), ("OUT", "Out of container", "")])

    @classmethod
    def poll(cls, context):
        return UIB_OT_remove.poll(context)

    def execute(self, context):
        s = settings(context)
        elems = s.elements
        a = s.active_index
        b = tree.block_end(elems, a)
        indent = elems[a].indent
        if self.direction == "IN":
            p = a - 1
            while p >= 0 and elems[p].indent > indent:
                p -= 1
            if p < 0 or elems[p].indent != indent or not el.DEFS[elems[p].type].container:
                self.report({"INFO"}, "Put a container (Row, Box, Panel...) right above to move into it")
                return {"CANCELLED"}
            delta = 1
        else:
            if indent == 0:
                return {"CANCELLED"}
            # Move behind the parent's block so following siblings stay put.
            parent = a - 1
            while parent >= 0 and elems[parent].indent >= indent:
                parent -= 1
            target = tree.block_end(elems, parent)
            if target > b:
                for _ in range(b - a):
                    elems.move(a, target - 1)
                a = target - (b - a)
                b = target
            delta = -1
        for k in range(a, b):
            elems[k].indent += delta
        s.active_index = a
        tree.normalize(elems)
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_clear(bpy.types.Operator):
    """Remove every element from the project"""
    bl_idname = "ui_builder.clear"
    bl_label = "Clear Project"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = settings(context)
        s.elements.clear()
        s.active_index = 0
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_pick_icon(bpy.types.Operator):
    """Search Blender's built-in icons"""
    bl_idname = "ui_builder.pick_icon"
    bl_label = "Pick Icon"
    bl_property = "icon"
    bl_options = {"REGISTER", "UNDO"}

    icon: EnumProperty(items=icons.icon_items, name="Icon")

    @classmethod
    def poll(cls, context):
        return UIB_OT_remove.poll(context)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"FINISHED"}

    def execute(self, context):
        s = settings(context)
        s.elements[s.active_index].icon = self.icon
        _redraw(context)
        return {"FINISHED"}


def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            area.tag_redraw()


classes = (UIB_OT_add, UIB_OT_remove, UIB_OT_duplicate, UIB_OT_move, UIB_OT_indent,
           UIB_OT_clear, UIB_OT_pick_icon)
