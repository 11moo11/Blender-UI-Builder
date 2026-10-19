"""Schematic maps of the Blender window showing where panels and elements live."""

import textwrap

from . import elements as el
from . import tree

_OVERVIEW_CELL = {"VIEW_3D": "VIEWPORT", "PROPERTIES": "PROPERTIES", "OUTLINER": "OUTLINER",
                  "DOPESHEET_EDITOR": "TIMELINE", "TOP_BAR": "TOP_BAR"}


class Entry:
    def __init__(self, label, space, cell, title, node=None):
        self.label, self.space, self.cell, self.title, self.node = label, space, cell, title, node


def entries(s):
    """Every place something of the project lives, plus the one for the selected element."""
    roots = tree.build(s.elements)
    nodes = list(tree.walk(roots))
    out, selected = [], None
    project = el.project_place(s)
    sel_node = nodes[s.active_index] if 0 <= s.active_index < len(nodes) else None

    def for_place(label, place, node):
        space, cell = place.cell()
        return Entry(label, space, cell, place.title(), node)

    loose = [n for n in roots if not n.is_panel]
    if loose:
        out.append(for_place("Main panel (loose elements)", project, None))
    for n in roots:
        if n.is_panel:
            out.append(for_place(n.elem.label or n.name or "Panel", el.panel_place(n.elem, s), n))
    for n in nodes:
        if n.outside is n:
            title, space, cell = el.LOCATIONS[n.elem.location]
            note = " - " + n.elem.location_note if n.elem.location_note else ""
            if space:
                out.append(Entry(n.elem.label or n.name, space, cell, title + note, n))
            else:
                out.append(Entry(n.elem.label or n.name, None, None, title + note, n))

    if sel_node is not None:
        if sel_node.outside is not None:
            owner = sel_node.outside
            selected = next((e for e in out if e.node is owner), None)
        else:
            root = sel_node.root_panel
            if root is not None:
                selected = next((e for e in out if e.node is root), None)
            else:
                selected = next((e for e in out if e.label.startswith("Main panel")), None)
    return out, selected, sel_node


def _cell(layout, s, text, state, scale=1.0):
    row = layout.row(align=True)
    row.scale_y = scale
    if state == "hot":
        row.alert = True
    row.prop(s, "map_on" if state else "map_off", text=text, toggle=True)


def wrap_label(layout, text, width=38, icon="NONE"):
    col = layout.column(align=True)
    for i, line in enumerate(textwrap.wrap(text, width) or [""]):
        col.label(text=line, icon=icon if i == 0 else "BLANK1")


def draw_overview(layout, s, entries_, selected):
    used = {_OVERVIEW_CELL.get(e.space, "OTHER") for e in entries_ if e.space}
    hot = _OVERVIEW_CELL.get(selected.space, "OTHER") if selected and selected.space else None

    def st(key):
        return "hot" if key == hot else "used" if key in used else None

    col = layout.column(align=True)
    _cell(col, s, "Top Bar", st("TOP_BAR"))
    sp = col.split(factor=0.66, align=True)
    left, right = sp.column(align=True), sp.column(align=True)
    _cell(left, s, "3D Viewport", st("VIEWPORT"), 5.5)
    _cell(right, s, "Outliner", st("OUTLINER"), 2.3)
    _cell(right, s, "Properties", st("PROPERTIES"), 3.0)
    bottom = col.split(factor=0.5, align=True)
    _cell(bottom.column(align=True), s, "Timeline", st("TIMELINE"))
    _cell(bottom.column(align=True), s, "Other Editors", st("OTHER"))


def draw_detail(layout, s, entry):
    """Zoomed map of the editor the selected thing lives in, with the exact region lit."""
    space, cell = entry.space, entry.cell
    title = el.SPACE_TITLES.get(space, space.title())
    col = layout.column(align=True)
    if space == "PROPERTIES":
        sp = col.split(factor=0.22, align=True)
        _cell(sp.column(align=True), s, "Tabs", None, 4)
        _cell(sp.column(align=True), s, "Tab content", "hot", 4)
        return
    if space in ("OUTLINER", "TOP_BAR", "DOPESHEET_EDITOR"):
        _cell(col, s, title, "hot", 2)
        return
    _cell(col, s, "%s header" % title, "hot" if cell == "HEADER" else None)
    sp = col.split(factor=0.14, align=True)
    tools = sp.column(align=True)
    rest = sp.column(align=True)
    sp2 = rest.split(factor=0.78, align=True)
    main, side = sp2.column(align=True), sp2.column(align=True)
    _cell(tools, s, "T", "hot" if cell == "TOOLBAR" else None, 4.5)
    _cell(main, s, title, "hot" if cell == "MAIN" else None, 4.5)
    _cell(side, s, "N", "hot" if cell == "SIDEBAR" else None, 4.5)
