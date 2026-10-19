"""Turns the flat, indent-based element list into a tree."""

from .elements import DEFS


class Node:
    __slots__ = ("elem", "index", "children", "parent", "name")

    def __init__(self, elem, index, parent):
        self.elem = elem
        self.index = index
        self.parent = parent
        self.children = []
        self.name = ""  # unique code identifier, assigned by the exporter

    @property
    def is_panel(self):
        """A real bpy Panel: a PANEL at the root or directly inside another real panel."""
        return self.elem.type == "PANEL" and (self.parent is None or self.parent.is_panel)

    @property
    def is_collapsible(self):
        """Box with a toggle header (COLLAPSE, or a PANEL nested in a non-panel container)."""
        return self.elem.type == "COLLAPSE" or (self.elem.type == "PANEL" and not self.is_panel)


def build(elements):
    """Return the root nodes. Over-deep indents are clamped to the nearest valid parent."""
    roots, stack = [], []
    for i, e in enumerate(elements):
        depth = min(max(e.indent, 0), len(stack))
        del stack[depth:]
        parent = stack[-1] if stack else None
        node = Node(e, i, parent)
        (parent.children if parent else roots).append(node)
        d = DEFS.get(e.type)
        if d is not None and d.container:
            stack.append(node)
    return roots


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n.children)


def block_end(elements, i):
    """Index just past element i and all of its descendants."""
    base = elements[i].indent
    j = i + 1
    while j < len(elements) and elements[j].indent > base:
        j += 1
    return j


def normalize(elements):
    """Make indents consistent: an element may only be nested inside a container."""
    for i, e in enumerate(elements):
        if i == 0:
            e.indent = 0
            continue
        prev = elements[i - 1]
        limit = prev.indent + (1 if DEFS[prev.type].container else 0)
        e.indent = max(0, min(e.indent, limit))
