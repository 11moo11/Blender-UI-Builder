"""Element catalogue: every UI element the builder can create, plus shared helpers."""

import keyword
import re

from .icons import valid_icon

# Categories, in the order they appear in the Add menu.
CATEGORIES = (
    ("LAYOUT", "Layout", "SNAP_GRID"),
    ("TEXT", "Text", "TEXT"),
    ("PROPS", "Properties", "PROPERTIES"),
    ("ACTIONS", "Buttons & Menus", "PLAY"),
    ("TEMPLATES", "Templates", "OUTLINER"),
)


class Def:
    """Static description of one element type."""

    def __init__(self, id, label, category, icon, *, container=False, ident=True,
                 icon_ok=True, desc=False, help=""):
        self.id = id
        self.label = label
        self.category = category
        self.icon = icon
        self.container = container  # may hold child elements
        self.ident = ident  # generates a code identifier (property/operator/class)
        self.icon_ok = icon_ok  # user may pick an icon
        self.desc = desc  # has a tooltip/description
        self.help = help


_DEFS = (
    # --- Layout -----------------------------------------------------------
    Def("PANEL", "Panel", "LAYOUT", "WINDOW", container=True, icon_ok=False,
        help="A panel. Inside another panel it becomes a sub-panel."),
    Def("COLLAPSE", "Collapsible Box", "LAYOUT", "TRIA_DOWN", container=True, icon_ok=False,
        help="A box with a clickable header that hides its contents."),
    Def("ROW", "Row", "LAYOUT", "ALIGN_JUSTIFY", container=True, ident=False, icon_ok=False,
        help="Lays children out left to right."),
    Def("COLUMN", "Column", "LAYOUT", "LINENUMBERS_ON", container=True, ident=False, icon_ok=False,
        help="Lays children out top to bottom."),
    Def("BOX", "Box", "LAYOUT", "MESH_PLANE", container=True, ident=False, icon_ok=False,
        help="Draws children inside a framed box."),
    Def("SPLIT", "Split", "LAYOUT", "SNAP_EDGE", container=True, ident=False, icon_ok=False,
        help="Splits the width by a factor between its children."),
    Def("GRID", "Grid", "LAYOUT", "MESH_GRID", container=True, ident=False, icon_ok=False,
        help="Flowing grid (layout.grid_flow)."),
    Def("SEPARATOR", "Separator", "LAYOUT", "REMOVE", ident=False, icon_ok=False,
        help="Empty gap or divider line."),
    Def("SPACER", "Spacer", "LAYOUT", "DOT", ident=False, icon_ok=False,
        help="Vertical gap of adjustable size."),
    # --- Text -------------------------------------------------------------
    Def("LABEL", "Label", "TEXT", "TEXT", ident=False, help="A line of text, optionally with an icon."),
    Def("TEXT_LINES", "Text Block", "TEXT", "ALIGN_LEFT", ident=False, icon_ok=False,
        help="Several labels in a column. Separate lines with '|'."),
    # --- Properties -------------------------------------------------------
    Def("BOOL", "Checkbox", "PROPS", "CHECKBOX_HLT", desc=True, help="Boolean property."),
    Def("INT", "Integer", "PROPS", "MOD_ARRAY", desc=True, help="Integer field."),
    Def("FLOAT", "Float", "PROPS", "IPO_LINEAR", desc=True, help="Float field."),
    Def("SLIDER", "Slider", "PROPS", "IPO_EASE_IN_OUT", desc=True, help="Float shown as a slider."),
    Def("FACTOR", "Factor", "PROPS", "NODE_COMPOSITING", desc=True, help="0-1 factor (subtype FACTOR)."),
    Def("PERCENT", "Percentage", "PROPS", "MOD_OPACITY", desc=True, help="0-100 percentage."),
    Def("ANGLE", "Angle", "PROPS", "DRIVER_ROTATIONAL_DIFFERENCE", desc=True, help="Rotation value in degrees."),
    Def("DISTANCE", "Distance", "PROPS", "DRIVER_DISTANCE", desc=True, help="Length with scene units."),
    Def("STRING", "Text Field", "PROPS", "FONT_DATA", desc=True, help="String property."),
    Def("FILEPATH", "File Path", "PROPS", "FILE", desc=True, help="File picker."),
    Def("DIRPATH", "Folder Path", "PROPS", "FILE_FOLDER", desc=True, help="Folder picker."),
    Def("ENUM", "Dropdown", "PROPS", "COLLAPSEMENU", desc=True,
        help="Enum property: dropdown, expanded buttons or tabs."),
    Def("COLOR", "Color", "PROPS", "COLOR", desc=True, help="RGB color."),
    Def("COLOR_ALPHA", "Color + Alpha", "PROPS", "IMAGE_RGB_ALPHA", desc=True, help="RGBA color."),
    Def("VEC2", "Vector 2D", "PROPS", "EMPTY_AXIS", desc=True, help="Two float fields."),
    Def("VEC3", "Vector 3D", "PROPS", "CON_LOCLIMIT", desc=True, help="X Y Z float fields."),
    Def("EULER", "Euler Rotation", "PROPS", "ORIENTATION_GIMBAL", desc=True, help="X Y Z rotation."),
    Def("POINTER", "Data-block Pointer", "PROPS", "OBJECT_DATA", desc=True,
        help="Pick an Object, Material, Collection, Image or World."),
    Def("SEARCH", "Search Field", "PROPS", "VIEWZOOM", desc=True,
        help="String with a searchable list of Blender data (prop_search)."),
    # --- Actions ----------------------------------------------------------
    Def("BUTTON", "Button", "ACTIONS", "PLAY", desc=True, help="Operator button. Exports an operator stub."),
    Def("MENU", "Dropdown Menu", "ACTIONS", "DOWNARROW_HLT", desc=True,
        help="A menu button. Items come from the options list."),
    Def("POPOVER", "Popover", "ACTIONS", "FULLSCREEN_ENTER", container=True, desc=True,
        help="Button that opens a floating panel containing its children."),
    # --- Templates --------------------------------------------------------
    Def("LIST", "List (UIList)", "TEMPLATES", "LONGDISPLAY", desc=True, help="Scrollable list of items."),
    Def("TEMPLATE_ID", "Data-block Selector", "TEMPLATES", "DUPLICATE", desc=True,
        help="template_ID selector with new/browse buttons."),
    Def("COLOR_PICKER", "Color Wheel", "TEMPLATES", "EYEDROPPER", desc=True,
        help="Large color wheel (template_color_picker)."),
    Def("IMAGE_PREVIEW", "Preview Image", "TEMPLATES", "IMAGE_DATA", ident=False, icon_ok=False,
        help="Large icon / thumbnail (template_icon). Supply the icon id in code."),
    Def("PROGRESS", "Progress Bar", "TEMPLATES", "TIME", desc=True, help="Progress bar (layout.progress)."),
)

DEFS = {d.id: d for d in _DEFS}


def defs_in(category):
    return [d for d in _DEFS if d.category == category]


# Attribute on the element that holds the previewed/default value for each type.
VALUE_ATTR = {
    "BOOL": "bool_value", "INT": "int_value", "FLOAT": "float_value",
    "SLIDER": "slider_value", "FACTOR": "factor_value", "PERCENT": "percent_value",
    "ANGLE": "angle_value", "DISTANCE": "distance_value", "STRING": "string_value",
    "FILEPATH": "file_value", "DIRPATH": "dir_value", "ENUM": "enum_value",
    "MENU": "enum_value", "COLOR": "color_value", "COLOR_PICKER": "color_value",
    "COLOR_ALPHA": "color_alpha_value", "VEC2": "vec2_value", "VEC3": "vec3_value",
    "EULER": "euler_value", "SEARCH": "string_value", "PROGRESS": "progress_factor",
}

POINTER_ATTR = {
    "OBJECT": "ptr_object", "MATERIAL": "ptr_material", "COLLECTION": "ptr_collection",
    "IMAGE": "ptr_image", "WORLD": "ptr_world",
}

# id_type -> (bpy.types name, template_ID new, template_ID open)
ID_TYPES = {
    "OBJECT": ("Object", "", ""),
    "MATERIAL": ("Material", "material.new", ""),
    "COLLECTION": ("Collection", "collection.new", ""),
    "IMAGE": ("Image", "image.new", "image.open"),
    "WORLD": ("World", "world.new", ""),
}

SEARCH_SOURCES = (
    "objects", "materials", "collections", "images", "meshes", "cameras", "lights",
    "worlds", "node_groups", "actions", "scenes", "texts", "fonts", "curves",
)

PLACEMENTS = {
    "VIEW_3D_UI": ("3D Viewport > Sidebar", "VIEW_3D", "UI", None),
    "IMAGE_EDITOR_UI": ("Image Editor > Sidebar", "IMAGE_EDITOR", "UI", None),
    "NODE_EDITOR_UI": ("Node Editor > Sidebar", "NODE_EDITOR", "UI", None),
    "SEQUENCE_EDITOR_UI": ("Video Sequencer > Sidebar", "SEQUENCE_EDITOR", "UI", None),
    "TEXT_EDITOR_UI": ("Text Editor > Sidebar", "TEXT_EDITOR", "UI", None),
    "CLIP_EDITOR_UI": ("Movie Clip Editor > Sidebar", "CLIP_EDITOR", "UI", None),
    "PROPS_SCENE": ("Properties > Scene tab", "PROPERTIES", "WINDOW", "scene"),
    "PROPS_OBJECT": ("Properties > Object tab", "PROPERTIES", "WINDOW", "object"),
    "PROPS_RENDER": ("Properties > Render tab", "PROPERTIES", "WINDOW", "render"),
    "PROPS_WORLD": ("Properties > World tab", "PROPERTIES", "WINDOW", "world"),
    "PROPS_DATA": ("Properties > Object Data tab", "PROPERTIES", "WINDOW", "data"),
    "PROPS_MATERIAL": ("Properties > Material tab", "PROPERTIES", "WINDOW", "material"),
    "PROPS_TOOL": ("Properties > Tool tab", "PROPERTIES", "WINDOW", "tool"),
}


def slugify(text, fallback="item"):
    """Lower-case python identifier made from arbitrary text."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", (text or "").strip()).strip("_").lower()
    if not s:
        s = fallback
    if s[0].isdigit():
        s = "n_" + s
    if keyword.iskeyword(s):
        s += "_"
    return s


def parse_enum_items(text):
    """'Option A, Option B' -> [('option_a', 'Option A'), ('option_b', 'Option B')] (unique ids)."""
    items, used = [], set()
    for raw in (text or "").split(","):
        name = raw.strip()
        if not name:
            continue
        ident = base = slugify(name)
        n = 2
        while ident in used:
            ident = "%s_%d" % (base, n)
            n += 1
        used.add(ident)
        items.append((ident, name))
    return items or [("none", "None")]


# --- Layout call specifications ----------------------------------------------
# Both the live preview and the code exporter are driven by these specs, so what
# you see in the mockup is exactly what the exported code draws.

class Ref:
    """Reference to the element's data: expands to (data, "property_name")."""

    def __init__(self, kind):
        self.kind = kind  # 'value' | 'items' | 'index'


class Sym:
    """Symbolic value each backend resolves in its own way."""

    def __init__(self, name):
        self.name = name  # 'bpy.data' | 'operator' | 'uilist' | 'menu' | 'popover' | 'value'


class Spec:
    def __init__(self, method, args=(), kwargs=None):
        self.method = method
        self.args = list(args)
        self.kwargs = kwargs or {}


_API_DEFAULTS = {
    ("row", "align"): False, ("column", "align"): False, ("split", "align"): False,
    ("split", "factor"): 0.0, ("grid_flow", "align"): False, ("grid_flow", "columns"): 0,
    ("grid_flow", "row_major"): False, ("grid_flow", "even_columns"): False,
    ("grid_flow", "even_rows"): False,
}


def _clean(method, kw):
    return {k: v for k, v in kw.items() if _API_DEFAULTS.get((method, k), object()) != v}


def _text_icon(e):
    kw = {"text": e.label}
    icon = valid_icon(e.icon) if DEFS[e.type].icon_ok else None
    if icon:
        kw["icon"] = icon
    return kw


def container_spec(e):
    """(layout method, kwargs) for plain layout containers."""
    t = e.type
    if t == "ROW":
        return "row", _clean("row", {"align": e.align})
    if t == "COLUMN":
        return "column", _clean("column", {"align": e.align})
    if t == "BOX":
        return "box", {}
    if t == "SPLIT":
        return "split", _clean("split", {"factor": round(e.split_factor, 3), "align": e.align})
    if t == "GRID":
        return "grid_flow", _clean("grid_flow", {
            "row_major": e.grid_row_major, "columns": e.grid_columns,
            "even_columns": e.grid_even_columns, "even_rows": e.grid_even_rows,
            "align": e.align})
    raise KeyError(t)


def layout_attrs(e, container):
    """Attribute assignments applied to the layout an element draws into."""
    attrs = []
    if not e.enabled:
        attrs.append(("enabled", False))
    if not e.active:
        attrs.append(("active", False))
    if e.alert:
        attrs.append(("alert", True))
    if e.scale_x != 1.0:
        attrs.append(("scale_x", round(e.scale_x, 3)))
    if e.scale_y != 1.0:
        attrs.append(("scale_y", round(e.scale_y, 3)))
    if e.emboss != "NORMAL":
        attrs.append(("emboss", e.emboss))
    if e.alignment != "EXPAND":
        attrs.append(("alignment", e.alignment))
    if container and e.prop_split:
        attrs.append(("use_property_split", True))
        attrs.append(("use_property_decorate", False))
    return attrs


def leaf_specs(e, export=False):
    """Layout calls that draw a non-container element."""
    t = e.type
    kw = _text_icon(e)
    value = [Ref("value")]
    if t == "LABEL":
        return [Spec("label", [], kw)]
    if t == "TEXT_LINES":
        specs = []
        for i, line in enumerate(e.label.split("|")):
            specs.append(Spec("label", [], {"text": line.strip()}))
        return specs
    if t == "SEPARATOR":
        skw = {}
        if e.separator_style != "AUTO":
            skw["type"] = e.separator_style
        if e.spacer_factor != 1.0:
            skw["factor"] = round(e.spacer_factor, 3)
        return [Spec("separator", [], skw)]
    if t == "SPACER":
        return [Spec("separator", [], {"factor": round(e.spacer_factor, 3)})]
    if t == "BOOL":
        if e.bool_style == "TOGGLE":
            kw["toggle"] = True
        elif e.bool_style == "ICON" and "icon" in kw:
            kw["text"] = ""
            kw["toggle"] = True
        return [Spec("prop", value, kw)]
    if t == "SLIDER":
        kw["slider"] = True
        return [Spec("prop", value, kw)]
    if t == "ENUM":
        if e.enum_style == "TABS":
            return [Spec("prop_tabs_enum", value, {})]
        if e.enum_style == "EXPAND":
            kw["expand"] = True
        return [Spec("prop", value, kw)]
    if t in ("INT", "FLOAT", "FACTOR", "PERCENT", "ANGLE", "DISTANCE", "STRING", "FILEPATH",
             "DIRPATH", "COLOR", "COLOR_ALPHA", "VEC2", "VEC3", "EULER", "POINTER"):
        return [Spec("prop", value, kw)]
    if t == "SEARCH":
        return [Spec("prop_search", value + [Sym("bpy.data"), e.search_source], kw)]
    if t == "BUTTON":
        return [Spec("operator", [Sym("operator")], kw)]
    if t == "MENU":
        if export:
            return [Spec("menu", [Sym("menu")], kw)]
        return [Spec("prop_menu_enum", value, kw)]
    if t == "POPOVER":
        return [Spec("popover", [], dict(kw, panel=Sym("popover")))]
    if t == "TEMPLATE_ID":
        _, new, open_ = ID_TYPES[e.id_type]
        tkw = {}
        if new:
            tkw["new"] = new
        if open_:
            tkw["open"] = open_
        return [Spec("template_ID", value, tkw)]
    if t == "IMAGE_PREVIEW":
        return [Spec("template_icon", [], {"icon_value": Sym("preview_icon"), "scale": round(e.preview_scale, 2)})]
    if t == "COLOR_PICKER":
        return [Spec("template_color_picker", value, {"value_slider": True})]
    if t == "PROGRESS":
        return [Spec("progress", [], {"factor": Sym("value"), "type": e.progress_type, "text": e.label})]
    if t == "LIST":
        return [Spec("template_list", [Sym("uilist"), "", Ref("items"), Ref("index")],
                     {"rows": e.list_rows})]
    raise KeyError(t)


def value_attr(e):
    """Name of the element attribute holding this element's value."""
    if e.type in ("POINTER", "TEMPLATE_ID"):
        return POINTER_ATTR[e.id_type]
    return VALUE_ATTR[e.type]


# --- Where things live in the Blender window ---------------------------------------
import bpy  # noqa: E402

SPACE_ITEMS = [(i.identifier, i.name, "") for i in bpy.types.Panel.bl_rna.properties["bl_space_type"].enum_items]
REGION_ITEMS = [(i.identifier, i.name, "") for i in bpy.types.Panel.bl_rna.properties["bl_region_type"].enum_items]
SPACE_TITLES = {k: v for k, v, _ in SPACE_ITEMS}
REGION_TITLES = {
    "UI": "Sidebar (N panel)", "HEADER": "Header / dropdown", "TOOL_HEADER": "Tool settings bar",
    "TOOLS": "Toolbar", "WINDOW": "Main area", "FOOTER": "Footer", "TOOL_PROPS": "Tool properties",
}

# Elements that are not drawn by their panel at all (draw handlers, overlays, header buttons...)
# id -> (title, space, cell)
LOCATIONS = {
    "PANEL": ("In its panel", None, None),
    "VIEWPORT": ("3D Viewport (overlay / gizmo / draw handler)", "VIEW_3D", "MAIN"),
    "VP_HEADER": ("3D Viewport header", "VIEW_3D", "HEADER"),
    "TOOLBAR": ("3D Viewport toolbar", "VIEW_3D", "TOOLBAR"),
    "SIDEBAR": ("3D Viewport sidebar", "VIEW_3D", "SIDEBAR"),
    "IMAGE_EDITOR": ("Image Editor", "IMAGE_EDITOR", "MAIN"),
    "TOP_BAR": ("Top bar", "TOP_BAR", "MAIN"),
    "OUTLINER": ("Outliner", "OUTLINER", "MAIN"),
    "PROPERTIES": ("Properties editor", "PROPERTIES", "MAIN"),
    "TIMELINE": ("Timeline", "DOPESHEET_EDITOR", "MAIN"),
    "POPUP": ("Popup / dialog window", None, None),
}
LOCATION_ITEMS = [(k, v[0], "") for k, v in LOCATIONS.items()]


class Place:
    """Where a panel is registered: bl_space_type / bl_region_type / bl_context / category / parent."""

    def __init__(self, space, region, context=None, category="", parent=""):
        self.space, self.region, self.context = space, region, context or None
        self.category, self.parent = category, parent or ""

    def cell(self):
        """(space, cell) used by the location maps."""
        if self.space in ("PROPERTIES", "OUTLINER", "TOP_BAR"):
            return self.space, "MAIN"
        if self.region == "UI":
            return self.space, "SIDEBAR"
        if self.region in ("HEADER", "TOOL_HEADER", "FOOTER") or self.parent:
            return self.space, "HEADER"
        if self.region == "TOOLS":
            return self.space, "TOOLBAR"
        return self.space, "MAIN"

    def title(self):
        s = SPACE_TITLES.get(self.space, self.space.title())
        if self.space == "PROPERTIES":
            return "Properties editor > %s tab" % (self.context or "any").title()
        where = REGION_TITLES.get(self.region, self.region.title())
        text = "%s > %s" % (s, where)
        if self.region == "UI" and self.category:
            text += " > tab '%s'" % self.category
        if self.parent:
            text += " > inside %s" % self.parent
        return text


def project_place(settings):
    _, space, region, ctx = PLACEMENTS[settings.placement]
    return Place(space, region, ctx, settings.category)


def panel_place(e, settings):
    """Resolved Place of a root panel element."""
    mode = e.panel_placement
    if mode == "PROJECT":
        return project_place(settings)
    if mode == "CUSTOM":
        return Place(e.p_space, e.p_region, e.p_context, e.p_category or settings.category, e.p_parent)
    _, space, region, ctx = PLACEMENTS[mode]
    return Place(space, region, ctx, e.p_category or settings.category, e.p_parent)
