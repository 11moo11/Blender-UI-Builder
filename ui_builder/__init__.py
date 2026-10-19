bl_info = {
    "name": "UI Builder",
    "author": "11moo11",
    "version": (1, 3, 1),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > UI Builder",
    "description": "Design Blender addon UI mockups visually and export them as Python or an LLM prompt",
    "doc_url": "https://github.com/11moo11/Blender-UI-Builder",
    "tracker_url": "https://github.com/11moo11/Blender-UI-Builder/issues",
    "category": "Interface",
}

if "bpy" in locals():  # F8 / Reload Scripts: pick up edited submodules
    import importlib
    for _m in (icons, elements, tree, properties, preview, operators, export, project, importer,
               import_ops, locmap, updater, preferences, ui):
        importlib.reload(_m)
else:
    from . import (icons, elements, tree, properties, preview, operators, export, project,
                   importer, import_ops, locmap, updater, preferences, ui)

import bpy

_modules = (properties, preview, operators, project, import_ops, ui)


def register():
    preferences.register()
    for m in _modules:
        if m is properties:
            m.register()
        else:
            for c in m.classes:
                bpy.utils.register_class(c)


def unregister():
    for m in reversed(_modules):
        if m is properties:
            m.unregister()
        else:
            for c in reversed(m.classes):
                bpy.utils.unregister_class(c)
    preferences.unregister()


if __name__ == "__main__":
    register()
