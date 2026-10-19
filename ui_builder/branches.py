"""Keeps one 'Option' row under every Choice (enum) element, one per option.

Controls placed under an Option row are shown only while that option is selected, in the
mockup and in the exported code.
"""

import contextlib

from . import elements as el
from . import tree

_suspended = 0


@contextlib.contextmanager
def no_sync():
    """Suspend automatic syncing (bulk edits hold references that a sync would invalidate)."""
    global _suspended
    _suspended += 1
    try:
        yield
    finally:
        _suspended -= 1


def _parent_index(elems, i):
    indent = elems[i].indent
    p = i - 1
    while p >= 0 and elems[p].indent >= indent:
        p -= 1
    return p if p >= 0 and indent > 0 else -1


def _direct_children(elems, i, type_id=None):
    """Start indexes of the direct children of element i (optionally of one type)."""
    out, end, j = [], tree.block_end(elems, i), i + 1
    while j < end:
        if elems[j].indent == elems[i].indent + 1 and (type_id is None or elems[j].type == type_id):
            out.append(j)
        j = tree.block_end(elems, j)
    return out


def _remove_stray_options(elems):
    """Option rows that are not directly under a Choice are dissolved (their contents move up)."""
    i = 0
    while i < len(elems):
        if elems[i].type == "OPTION":
            p = _parent_index(elems, i)
            if p < 0 or elems[p].type != "ENUM":
                end = tree.block_end(elems, i)
                for k in range(i + 1, end):
                    elems[k].indent -= 1
                elems.remove(i)
                continue
        i += 1


def strip_options(elems, i):
    """Remove the Option rows of Choice i, lifting what is inside them one level."""
    for j in reversed(_direct_children(elems, i, "OPTION")):
        end = tree.block_end(elems, j)
        for k in range(j + 1, end):
            elems[k].indent -= 1
        elems.remove(j)


def sync_options(s, i):
    from .operators import new_element  # late import: operators imports this module
    elems = s.elements
    if not (0 <= i < len(elems)) or elems[i].type != "ENUM":
        return
    ind = elems[i].indent + 1
    desired = el.parse_enum_items(elems[i].enum_items)
    kids = _direct_children(elems, i, "OPTION")

    # 1. match existing rows to options: by identifier first, then the leftovers by position (renames)
    match = {}  # desired position -> kid start index
    free_kids = list(kids)
    for pos, (oid, _) in enumerate(desired):
        for k in free_kids:
            if elems[k].option_id == oid:
                match[pos] = k
                free_kids.remove(k)
                break
    for pos in range(len(desired)):
        if pos not in match and free_kids:
            match[pos] = free_kids.pop(0)
    for pos, k in match.items():
        oid, name = desired[pos]
        if elems[k].option_id != oid:
            elems[k].option_id = oid
        if elems[k].label != name:
            elems[k].label = name

    # 2. rows whose option is gone: delete if empty, otherwise keep and flag
    for k in sorted(free_kids, reverse=True):
        if tree.block_end(elems, k) == k + 1:
            elems.remove(k)
        elif not elems[k].label.endswith("(removed option)"):
            elems[k].label = "%s (removed option)" % elems[k].label

    # 3. new options get a fresh row at the end of the Choice's block
    for pos, (oid, name) in enumerate(desired):
        if pos in match:
            continue
        end = tree.block_end(elems, i)
        new_element(s, "OPTION", end, ind, name)
        row = elems[end]
        row.auto_ident = False
        row.option_id = oid
        icons = [x.strip() for x in elems[i].enum_icons.split(",")]
        if pos < len(icons) and icons[pos]:
            row.icon = icons[pos]

    # 4. order the rows like the options, right below the Choice
    cursor = i + 1
    for oid, _ in desired:
        rows = [k for k in _direct_children(elems, i, "OPTION") if elems[k].option_id == oid]
        if not rows:
            continue
        a = rows[0]
        b = tree.block_end(elems, a)
        if a != cursor:
            for k in range(b - a):
                elems.move(a + k, cursor + k)
        cursor += b - a


def option_icons(element, context):
    """{option id: icon name} for the Option rows under a Choice (used for the mockup's button icons)."""
    from .icons import valid_icon
    try:
        s = context.scene.ui_builder
        elems = s.elements
        for i, e in enumerate(elems):
            if e == element:
                out = {}
                for k in _direct_children(elems, i, "OPTION"):
                    icon = valid_icon(elems[k].icon)
                    if icon:
                        out[elems[k].option_id] = icon
                return out
    except Exception:
        pass
    return {}


def sync_all(s):
    if _suspended:
        return
    with no_sync():
        _remove_stray_options(s.elements)
    i = 0
    while i < len(s.elements):
        if s.elements[i].type == "ENUM":
            sync_options(s, i)
        i += 1


def sync_for(element, context):
    """Update callback of Choice.enum_items."""
    if _suspended or element.type != "ENUM":
        return
    s = context.scene.ui_builder
    for i, e in enumerate(s.elements):
        if e == element:
            sync_options(s, i)
            return
