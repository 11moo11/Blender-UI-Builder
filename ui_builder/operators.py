"""Operators that edit the element list."""

import contextlib

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import elements as el
from . import branches, icons, tree
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
    if active.type == "ENUM":  # a Choice's contents go under its options: add as a sibling instead
        return tree.block_end(elems, i), active.indent
    if el.DEFS[active.type].container:
        if active.fold:  # its contents are hidden, so "below" means after the whole folded block
            return tree.block_end(elems, i), active.indent
        return i + 1, active.indent + 1  # directly below the container row: its first child
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
        branches.sync_all(s)
        _redraw(context)
        return {"FINISHED"}


@contextlib.contextmanager
def operand(s):
    """Make sure the elements an operator acts on carry `selected` (falls back to the active one)
    and keep the active row pointing at the same element afterwards."""
    elems = s.elements
    temp = None
    if not any(e.selected for e in elems) and 0 <= s.active_index < len(elems):
        temp = s.active_index
        elems[temp].selected = True
    if 0 <= s.active_index < len(elems):
        elems[s.active_index].marker = True
    try:
        yield
    finally:
        elems = s.elements
        for i, e in enumerate(elems):
            if e.marker:
                s.active_index = i
                e.marker = False
        if temp is not None:
            for e in elems:
                e.selected = False


def _tops(elems):
    """Start index of every selected block that is not inside another selected block."""
    tops, i = [], 0
    while i < len(elems):
        if elems[i].selected:
            tops.append(i)
            i = tree.block_end(elems, i)
        else:
            i += 1
    return tops


def _prev_sibling(elems, a):
    indent = elems[a].indent
    p = a - 1
    while p >= 0 and elems[p].indent > indent:
        p -= 1
    return p if p >= 0 and elems[p].indent == indent else None


class _ElementOp(bpy.types.Operator):
    @classmethod
    def poll(cls, context):
        s = settings(context)
        return len(s.elements) > 0


class UIB_OT_remove(_ElementOp):
    """Remove the selected elements (or the active one) and everything inside them"""
    bl_idname = "ui_builder.remove"
    bl_label = "Remove Elements"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = settings(context)
        with operand(s):
            for a in reversed(_tops(s.elements)):
                end = tree.block_end(s.elements, a)
                for _ in range(end - a):
                    s.elements.remove(a)
        s.active_index = max(0, min(s.active_index, len(s.elements) - 1))
        branches.sync_all(s)
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


class UIB_OT_duplicate(_ElementOp):
    """Duplicate the selected elements (or the active one) with everything inside them"""
    bl_idname = "ui_builder.duplicate"
    bl_label = "Duplicate Elements"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = settings(context)
        first_copy = None
        with operand(s):
            elems = s.elements
            runs = []  # contiguous groups of selected blocks are copied together, as one group
            for a in _tops(elems):
                end = tree.block_end(elems, a)
                if runs and runs[-1][1] == a:
                    runs[-1][1] = end
                else:
                    runs.append([a, end])
            with branches.no_sync():
                for a, end in reversed(runs):
                    for k in range(end - a):
                        elems.add()  # may reallocate, so look elements up by index afterwards
                        _copy_props(elems[a + k], elems[len(elems) - 1])
                        elems.move(len(elems) - 1, end + k)
                        elems[end + k].marker = False
                    for k in range(a, end):
                        elems[k].selected = False  # the copies stay selected
                    first_copy = end
        if first_copy is not None:
            s.active_index = first_copy
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_move(_ElementOp):
    """Move the selected elements (with their children) among their siblings"""
    bl_idname = "ui_builder.move"
    bl_label = "Move Elements"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("UP", "Up", ""), ("DOWN", "Down", "")])

    def execute(self, context):
        s = settings(context)
        moved = False
        with operand(s):
            elems = s.elements
            tops = _tops(elems)
            blocked = set()  # starts of blocks that could not move (neighbours must not jump over them)
            if self.direction == "UP":
                for a in tops:
                    b = tree.block_end(elems, a)
                    p = _prev_sibling(elems, a)
                    if p is None or p in blocked:
                        blocked.add(a)
                        continue
                    for k in range(b - a):
                        elems.move(a + k, p + k)
                    moved = True
            else:
                for a in reversed(tops):
                    b = tree.block_end(elems, a)
                    if b >= len(elems) or elems[b].indent != elems[a].indent or b in blocked:
                        blocked.add(a)
                        continue
                    c = tree.block_end(elems, b)
                    for k in range(c - b):
                        elems.move(b + k, a + k)
                    moved = True
        branches.sync_all(s)  # Option rows always follow the Choice's option order
        _redraw(context)
        return {"FINISHED"} if moved else {"CANCELLED"}


class UIB_OT_indent(_ElementOp):
    """Move the selected elements into the container above them, or back out of their container"""
    bl_idname = "ui_builder.indent"
    bl_label = "Change Nesting"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(items=[("IN", "Into container above", ""), ("OUT", "Out of container", "")])

    def execute(self, context):
        s = settings(context)
        changed = 0
        with operand(s):
            elems = s.elements
            tops = _tops(elems)
            if self.direction == "IN":
                for a in tops:
                    b = tree.block_end(elems, a)
                    p = _prev_sibling(elems, a)
                    if p is None or not el.can_nest(elems[p].type):
                        continue
                    for k in range(a, b):
                        elems[k].indent += 1
                    changed += 1
            else:
                for a in reversed(tops):  # last first, so the original order is kept
                    b = tree.block_end(elems, a)
                    indent = elems[a].indent
                    if indent == 0:
                        continue
                    parent = a - 1
                    while parent >= 0 and elems[parent].indent >= indent:
                        parent -= 1
                    target = tree.block_end(elems, parent)
                    if target > b:  # move behind the parent's block so later siblings stay put
                        for _ in range(b - a):
                            elems.move(a, target - 1)
                        a, b = target - (b - a), target
                    for k in range(a, b):
                        elems[k].indent -= 1
                    changed += 1
            tree.normalize(elems)
        branches.sync_all(s)
        if not changed:
            self.report({"INFO"}, "Nothing to nest here: put a container (Row, Box, Panel...) right above "
                                  "to move into it" if self.direction == "IN" else "Already at the top level")
            return {"CANCELLED"}
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_replace(_ElementOp):
    """Change the type of the selected elements (or the active one), keeping their children and settings"""
    bl_idname = "ui_builder.replace"
    bl_label = "Replace Selected"
    bl_options = {"REGISTER", "UNDO"}

    type: EnumProperty(items=[(d.id, d.label, d.help) for d in el._DEFS])

    def execute(self, context):
        s = settings(context)
        new = el.DEFS[self.type]
        lifted = 0
        with operand(s):
            elems = s.elements
            # Every selected element, children of selected containers included only if selected themselves.
            for i in [i for i, e in enumerate(elems) if e.selected]:
                e = elems[i]
                old = el.DEFS[e.type]
                if e.type == self.type or e.type == "OPTION":
                    continue
                if e.type == "ENUM":  # leaving Choice: its Option rows dissolve, contents move up
                    branches.strip_options(elems, i)
                    e = elems[i]  # the removals above may have invalidated the old reference
                if not new.container:  # a leaf can't hold children: move them up one level
                    end = tree.block_end(elems, i)
                    for k in range(i + 1, end):
                        elems[k].indent -= 1
                        lifted += 1
                if e.label in ("", old.label):
                    e.label = new.label
                e.type = self.type
                if e.auto_ident or not e.ident:
                    e.ident = el.slugify(e.label, el.slugify(self.type))
                if self.type == "LIST":
                    ensure_mock_items(context.scene)
            tree.normalize(elems)
        branches.sync_all(s)
        if lifted:
            self.report({"INFO"}, "%d child element(s) were moved up a level" % lifted)
        _redraw(context)
        return {"FINISHED"}


class UIB_OT_select(bpy.types.Operator):
    """Change which elements are ticked (ticked elements are moved / nested / deleted together)"""
    bl_idname = "ui_builder.select"
    bl_label = "Select Elements"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(items=[
        ("ALL", "All", "Tick every element"),
        ("NONE", "None", "Untick everything"),
        ("INVERT", "Invert", "Flip every tick"),
        ("CHILDREN", "Add Children", "Also tick everything inside the ticked containers"),
        ("SIBLINGS", "Same Level", "Tick every element at the active element's nesting level")])

    def execute(self, context):
        s = settings(context)
        elems = s.elements
        if self.action == "ALL":
            for e in elems:
                e.selected = True
        elif self.action == "NONE":
            for e in elems:
                e.selected = False
        elif self.action == "INVERT":
            for e in elems:
                e.selected = not e.selected
        elif self.action == "CHILDREN":
            chosen = [i for i, e in enumerate(elems) if e.selected]
            for i in chosen:
                for k in range(i, tree.block_end(elems, i)):
                    elems[k].selected = True
        elif self.action == "SIBLINGS" and 0 <= s.active_index < len(elems):
            level = elems[s.active_index].indent
            for e in elems:
                e.selected = e.indent == level
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
        s = settings(context)
        return 0 <= s.active_index < len(s.elements)

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


classes = (UIB_OT_add, UIB_OT_remove, UIB_OT_duplicate, UIB_OT_move, UIB_OT_indent, UIB_OT_replace, UIB_OT_select,
           UIB_OT_clear, UIB_OT_pick_icon)
