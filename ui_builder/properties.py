"""Scene-level data model: the element list and builder settings."""

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty,
    IntProperty, PointerProperty, StringProperty,
)

from . import elements as el

_enum_cache = {}


def _enum_value_items(self, context):
    key = self.enum_items
    items = _enum_cache.get(key)
    if items is None:
        if len(_enum_cache) > 2000:
            _enum_cache.clear()
        items = [(ident, name, "") for ident, name in el.parse_enum_items(key)]
        _enum_cache[key] = items
    return items


def _on_label(self, context):
    if self.auto_ident:
        self.ident = el.slugify(self.label, el.slugify(self.type))


def _on_auto_ident(self, context):
    if self.auto_ident:
        _on_label(self, context)


_ALIGNMENT = [("EXPAND", "Expand", ""), ("LEFT", "Left", ""), ("CENTER", "Center", ""), ("RIGHT", "Right", "")]
_EMBOSS = [("NORMAL", "Normal", ""), ("NONE", "None", "Flat, no button background"),
           ("PULLDOWN_MENU", "Pulldown", ""), ("NONE_OR_STATUS", "None / Status", "")]
_ID_TYPES = [("OBJECT", "Object", ""), ("MATERIAL", "Material", ""), ("COLLECTION", "Collection", ""),
             ("IMAGE", "Image", ""), ("WORLD", "World", "")]


class UIB_Element(bpy.types.PropertyGroup):
    type: StringProperty(default="LABEL")
    label: StringProperty(name="Name", description="Text shown on the element", default="", update=_on_label)
    ident: StringProperty(name="Identifier",
                          description="Python identifier used for the generated property / operator / class")
    auto_ident: BoolProperty(name="Auto", description="Derive the identifier from the name",
                             default=True, update=_on_auto_ident)
    description: StringProperty(name="Tooltip", description="Tooltip / description in the exported code")
    icon: StringProperty(name="Icon", default="NONE")
    indent: IntProperty(default=0, min=0)
    expanded: BoolProperty(name="Expanded", default=True)

    # Layout modifiers
    enabled: BoolProperty(name="Enabled", description="layout.enabled", default=True)
    active: BoolProperty(name="Active", description="layout.active (greyed out when off)", default=True)
    alert: BoolProperty(name="Alert", description="layout.alert (red highlight)", default=False)
    scale_x: FloatProperty(name="Scale X", default=1.0, min=0.0, soft_max=3.0)
    scale_y: FloatProperty(name="Scale Y", default=1.0, min=0.0, soft_max=3.0)
    emboss: EnumProperty(name="Emboss", items=_EMBOSS, default="NORMAL")
    alignment: EnumProperty(name="Alignment", items=_ALIGNMENT, default="EXPAND")
    align: BoolProperty(name="Align", description="Join the children without gaps", default=False)
    prop_split: BoolProperty(name="Property Split",
                             description="use_property_split: label on the left, value on the right",
                             default=False)

    # Container options
    split_factor: FloatProperty(name="Factor", default=0.5, min=0.0, max=1.0, subtype="FACTOR")
    grid_columns: IntProperty(name="Columns", description="0 = automatic", default=0, min=0)
    grid_row_major: BoolProperty(name="Row Major", default=True)
    grid_even_columns: BoolProperty(name="Even Columns", default=True)
    grid_even_rows: BoolProperty(name="Even Rows", default=True)
    default_closed: BoolProperty(name="Closed by Default", default=False)
    header_checkbox: BoolProperty(name="Header Checkbox",
                                  description="Add an enable checkbox to the panel header", default=False)

    # Leaf options
    bool_style: EnumProperty(name="Style", default="CHECKBOX", items=[
        ("CHECKBOX", "Checkbox", ""), ("TOGGLE", "Toggle Button", ""), ("ICON", "Icon Toggle", "Needs an icon")])
    enum_style: EnumProperty(name="Style", default="DROPDOWN", items=[
        ("DROPDOWN", "Dropdown", ""), ("EXPAND", "Expanded Buttons", ""), ("TABS", "Tabs", "")])
    enum_items: StringProperty(name="Options", description="Comma separated option names",
                               default="Option A, Option B, Option C")
    separator_style: EnumProperty(name="Style", default="AUTO", items=[
        ("AUTO", "Auto", ""), ("SPACE", "Space", ""), ("LINE", "Line", "")])
    spacer_factor: FloatProperty(name="Size", default=1.0, min=0.0, soft_max=10.0)
    id_type: EnumProperty(name="Data Type", items=_ID_TYPES, default="OBJECT")
    search_source: EnumProperty(name="Search In", default="objects",
                                items=[(s, s.replace("_", " ").title(), "") for s in el.SEARCH_SOURCES])
    list_rows: IntProperty(name="Rows", default=4, min=1, max=20)
    progress_type: EnumProperty(name="Type", default="BAR", items=[("BAR", "Bar", ""), ("RING", "Ring", "")])
    use_range: BoolProperty(name="Limit Range", description="Export min / max for this property", default=False)
    range_min: FloatProperty(name="Min", default=0.0)
    range_max: FloatProperty(name="Max", default=1.0)

    # Values: shown in the mockup, exported as property defaults
    bool_value: BoolProperty(name="Value")
    int_value: IntProperty(name="Value")
    float_value: FloatProperty(name="Value")
    slider_value: FloatProperty(name="Value", min=0.0, max=1.0, default=0.5)
    factor_value: FloatProperty(name="Value", min=0.0, max=1.0, default=0.5, subtype="FACTOR")
    percent_value: FloatProperty(name="Value", min=0.0, max=100.0, default=50.0, subtype="PERCENTAGE")
    angle_value: FloatProperty(name="Value", subtype="ANGLE", unit="ROTATION")
    distance_value: FloatProperty(name="Value", subtype="DISTANCE", unit="LENGTH")
    string_value: StringProperty(name="Value")
    file_value: StringProperty(name="Value", subtype="FILE_PATH")
    dir_value: StringProperty(name="Value", subtype="DIR_PATH")
    enum_value: EnumProperty(name="Value", items=_enum_value_items)
    color_value: FloatVectorProperty(name="Value", size=3, subtype="COLOR", min=0.0, max=1.0,
                                     default=(0.8, 0.8, 0.8))
    color_alpha_value: FloatVectorProperty(name="Value", size=4, subtype="COLOR", min=0.0, max=1.0,
                                           default=(0.8, 0.8, 0.8, 1.0))
    vec2_value: FloatVectorProperty(name="Value", size=2)
    vec3_value: FloatVectorProperty(name="Value", size=3, subtype="XYZ")
    euler_value: FloatVectorProperty(name="Value", size=3, subtype="EULER")
    progress_factor: FloatProperty(name="Value", min=0.0, max=1.0, default=0.5, subtype="FACTOR")
    ptr_object: PointerProperty(type=bpy.types.Object, name="Value")
    ptr_material: PointerProperty(type=bpy.types.Material, name="Value")
    ptr_collection: PointerProperty(type=bpy.types.Collection, name="Value")
    ptr_image: PointerProperty(type=bpy.types.Image, name="Value")
    ptr_world: PointerProperty(type=bpy.types.World, name="Value")


class UIB_MockItem(bpy.types.PropertyGroup):
    name: StringProperty()


class UIB_ImportPanel(bpy.types.PropertyGroup):
    idname: StringProperty()
    label: StringProperty()
    parent_id: StringProperty()
    location: StringProperty()
    include: BoolProperty(name="Include", default=True)


_addon_items_cache = []


def _addon_items(self, context):
    from . import importer
    global _addon_items_cache
    items = [(m, name, "%d panel(s)" % n) for m, name, n in importer.addon_modules(exclude={__package__})]
    _addon_items_cache = items or [("NONE", "(no other addon with panels is enabled)", "")]
    return _addon_items_cache


_FORMATS = [
    ("PYTHON", "Python Addon", "A complete, registerable addon file"),
    ("LLM", "LLM Prompt", "Markdown brief: UI outline, property table and the generated code, ready to paste into an LLM"),
    ("JSON", "JSON Layout", "Project file that can be imported again"),
]
_MIN_VERSIONS = [("2.93.0", "2.93", ""), ("3.6.0", "3.6 LTS", ""), ("4.2.0", "4.2 LTS", ""), ("4.5.0", "4.5 LTS", "")]


class UIB_Settings(bpy.types.PropertyGroup):
    elements: CollectionProperty(type=UIB_Element)
    active_index: IntProperty()
    mock_items: CollectionProperty(type=UIB_MockItem)
    mock_index: IntProperty()

    addon_name: StringProperty(name="Addon Name", default="My Addon")
    author: StringProperty(name="Author", default="Your Name")
    prefix: StringProperty(name="Prefix", description="Short snake_case prefix for class names, operators and the property group",
                           default="my_addon")
    blender_min: EnumProperty(name="Min Blender", items=_MIN_VERSIONS, default="3.6.0")
    placement: EnumProperty(name="Location", default="VIEW_3D_UI",
                            items=[(k, v[0], "") for k, v in el.PLACEMENTS.items()])
    category: StringProperty(name="Tab", description="Sidebar tab name", default="My Addon")
    export_format: EnumProperty(name="Format", items=_FORMATS, default="PYTHON")

    import_module: EnumProperty(name="Addon", items=_addon_items,
                                description="Enabled addon whose panels will be imported")
    import_mode: EnumProperty(name="Mode", default="REPLACE", items=[
        ("REPLACE", "Replace Project", "Clear the project first and copy the addon's name / location settings"),
        ("APPEND", "Append", "Add the imported panels after the existing elements")])
    import_panels: CollectionProperty(type=UIB_ImportPanel)


classes = (UIB_Element, UIB_MockItem, UIB_ImportPanel, UIB_Settings)


def settings(context=None):
    return (context or bpy.context).scene.ui_builder


def ensure_mock_items(scene):
    s = scene.ui_builder
    if len(s.mock_items) == 0:
        for n in ("Item 1", "Item 2", "Item 3", "Item 4"):
            s.mock_items.add().name = n


def _load_post(_dummy):
    for sc in bpy.data.scenes:
        ensure_mock_items(sc)


def _init_timer():
    try:
        _load_post(None)
    except Exception:
        pass
    return None


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.ui_builder = PointerProperty(type=UIB_Settings)
    bpy.app.handlers.load_post.append(_load_post)
    bpy.app.timers.register(_init_timer, first_interval=0.2)


def unregister():
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    del bpy.types.Scene.ui_builder
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
