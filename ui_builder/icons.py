"""Access to Blender's built-in icon names."""

import bpy

_names = None
_items = None


def _enum_params():
    return bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items


def icon_names():
    """Set of every valid built-in icon identifier."""
    global _names
    if _names is None:
        _names = {i.identifier for i in _enum_params()}
    return _names


def valid_icon(name):
    """Return `name` if it is a usable icon, else None."""
    if name and name != "NONE" and name in icon_names():
        return name
    return None


def icon_items(self=None, context=None):
    """EnumProperty items for the icon search popup (kept alive in a module global)."""
    global _items
    if _items is None:
        _items = [("NONE", "No Icon", "", "X", 0)]
        for i in _enum_params():
            if i.identifier == "NONE":
                continue
            _items.append((i.identifier, i.name, "", i.value, len(_items)))
    return _items


def icon_id(name):
    """Numeric icon id for use with icon_value=."""
    for i in _enum_params():
        if i.identifier == name:
            return i.value
    return 0
