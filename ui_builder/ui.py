"""The builder interface (3D Viewport sidebar > UI Builder tab)."""

import bpy

from . import elements as el
from . import icons, preferences, updater
from .properties import settings


class UIB_UL_elements(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        d = el.DEFS.get(item.type)
        row = layout.row(align=True)
        for _ in range(item.indent):
            row.label(text="", icon="BLANK1")
        row.label(text="", icon=d.icon if d else "QUESTION")
        row.prop(item, "label", text="", emboss=False)
        if d:
            sub = row.row()
            sub.enabled = False
            sub.label(text=d.label)


def _add_menu(category, title, icon):
    ns = {"bl_label": title}

    def draw(self, context):
        for d in el.defs_in(category):
            op = self.layout.operator("ui_builder.add", text=d.label, icon=d.icon)
            op.type = d.id
        if category == "LAYOUT":
            op = self.layout.operator("ui_builder.add", text="Sub-panel", icon="WINDOW")
            op.type = "SUBPANEL"

    ns["draw"] = draw
    return type("UIB_MT_add_" + category.lower(), (bpy.types.Menu,), ns)


_add_menus = [(c, t, i, _add_menu(c, t, i)) for c, t, i in el.CATEGORIES]


class UIB_MT_add(bpy.types.Menu):
    bl_label = "Add Element"

    def draw(self, context):
        for category, title, icon, menu in _add_menus:
            self.layout.menu(menu.__name__, text=title, icon=icon)


class UIB_MT_project(bpy.types.Menu):
    bl_label = "Project"

    def draw(self, context):
        l = self.layout
        l.operator("ui_builder.load_example", icon="FILE_NEW")
        l.operator("ui_builder.import_json", icon="IMPORT")
        l.separator()
        l.operator("ui_builder.clear", icon="TRASH")


class UIB_PT_main(bpy.types.Panel):
    bl_label = "UI Builder"
    bl_idname = "UIB_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"

    def draw_header_preset(self, context):
        self.layout.menu("UIB_MT_project", text="", icon="DOWNARROW_HLT")

    def draw(self, context):
        layout = self.layout
        s = settings(context)
        st = updater.STATE
        if st.status in (st.AVAILABLE, st.INSTALLED):
            box = layout.box()
            box.alert = st.status == st.AVAILABLE
            box.label(text=st.message, icon="INFO")
            if st.status == st.AVAILABLE:
                box.operator("ui_builder.install_update", text="Update Now", icon="IMPORT")
            else:
                box.operator("ui_builder.reload_scripts", icon="FILE_REFRESH")

        row = layout.row()
        row.template_list("UIB_UL_elements", "", s, "elements", s, "active_index", rows=8)
        col = row.column(align=True)
        col.operator("ui_builder.remove", icon="REMOVE", text="")
        col.operator("ui_builder.duplicate", icon="DUPLICATE", text="")
        col.separator()
        col.operator("ui_builder.move", icon="TRIA_UP", text="").direction = "UP"
        col.operator("ui_builder.move", icon="TRIA_DOWN", text="").direction = "DOWN"
        col.separator()
        col.operator("ui_builder.indent", icon="FORWARD", text="").direction = "IN"
        col.operator("ui_builder.indent", icon="BACK", text="").direction = "OUT"
        big = layout.row()
        big.scale_y = 2.0
        big.menu("UIB_MT_add", text="Add Element", icon="ADD")
        if not len(s.elements):
            box = layout.box()
            box.label(text="Start with: Add Element > Layout > Panel", icon="INFO")
            box.operator("ui_builder.load_example", icon="FILE_NEW")


class UIB_PT_element(bpy.types.Panel):
    bl_label = "Selected Element"
    bl_idname = "UIB_PT_element"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"
    bl_parent_id = "UIB_PT_main"

    @classmethod
    def poll(cls, context):
        s = settings(context)
        return 0 <= s.active_index < len(s.elements)

    def draw(self, context):
        s = settings(context)
        draw_element(self.layout, s.elements[s.active_index])


def _pick_icon(layout, e):
    row = layout.row(align=True)
    icon = icons.valid_icon(e.icon)
    row.operator("ui_builder.pick_icon", text=e.icon if icon else "Pick Icon...", icon=icon or "VIEWZOOM")
    if e.icon != "NONE":
        row.prop(e, "icon", text="")


def draw_element(layout, e):
    d = el.DEFS[e.type]
    t = e.type
    layout.use_property_split = False
    col = layout.column()
    col.label(text=d.label, icon=d.icon)
    col.prop(e, "label", text="Name")
    if d.ident:
        row = col.row(align=True)
        row.prop(e, "ident", text="ID")
        row.prop(e, "auto_ident", text="", icon="LINKED" if e.auto_ident else "UNLINKED", toggle=True)
    if d.desc:
        col.prop(e, "description", text="Tooltip")
    if d.icon_ok:
        _pick_icon(col, e)

    col.separator()
    if t == "TEXT_LINES":
        col.label(text="Separate lines with |  in the name")
    elif t == "PANEL":
        col.prop(e, "default_closed")
        col.prop(e, "header_checkbox")
    elif t in ("ROW", "COLUMN", "SPLIT", "GRID"):
        col.prop(e, "align")
        if t == "SPLIT":
            col.prop(e, "split_factor")
        if t == "GRID":
            col.prop(e, "grid_columns")
            col.prop(e, "grid_row_major")
            col.prop(e, "grid_even_columns")
            col.prop(e, "grid_even_rows")
    elif t == "SEPARATOR":
        col.prop(e, "separator_style")
        col.prop(e, "spacer_factor")
    elif t == "SPACER":
        col.prop(e, "spacer_factor")
    elif t == "BOOL":
        col.prop(e, "bool_style")
        col.prop(e, "bool_value", text="Default")
    elif t in ("INT", "FLOAT", "SLIDER", "FACTOR", "PERCENT", "ANGLE", "DISTANCE", "STRING", "FILEPATH",
               "DIRPATH", "COLOR", "COLOR_ALPHA", "VEC2", "VEC3", "EULER", "SEARCH", "PROGRESS"):
        col.prop(e, el.value_attr(e), text="Default")
        if t == "SEARCH":
            col.prop(e, "search_source")
        if t == "PROGRESS":
            col.prop(e, "progress_type")
        if t in ("INT", "FLOAT", "SLIDER", "FACTOR", "PERCENT", "ANGLE", "DISTANCE"):
            col.prop(e, "use_range")
            if e.use_range:
                r = col.row(align=True)
                r.prop(e, "range_min")
                r.prop(e, "range_max")
    elif t in ("ENUM", "MENU"):
        col.prop(e, "enum_items")
        if t == "ENUM":
            col.prop(e, "enum_style")
        col.prop(e, "enum_value", text="Default")
    elif t in ("POINTER", "TEMPLATE_ID"):
        col.prop(e, "id_type")
    elif t == "LIST":
        col.prop(e, "list_rows")
    elif t == "BUTTON":
        sub = col.box()
        sub.label(text="Exports an operator stub", icon="INFO")

    box = layout.box()
    box.label(text="Layout Modifiers", icon="MODIFIER")
    m = box.column(align=True)
    m.prop(e, "enabled")
    m.prop(e, "active")
    m.prop(e, "alert")
    m.prop(e, "scale_x")
    m.prop(e, "scale_y")
    m.prop(e, "emboss")
    m.prop(e, "alignment")
    if d.container or t == "PANEL":
        m.prop(e, "prop_split")


class UIB_PT_export(bpy.types.Panel):
    bl_label = "Export"
    bl_idname = "UIB_PT_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"

    def draw(self, context):
        layout = self.layout
        s = settings(context)
        col = layout.column(align=True)
        col.prop(s, "addon_name")
        col.prop(s, "author")
        col.prop(s, "prefix")
        layout.separator()
        col = layout.column(align=True)
        col.prop(s, "placement", text="")
        if el.PLACEMENTS[s.placement][2] == "UI":
            col.prop(s, "category")
        col.prop(s, "blender_min")
        layout.separator()
        layout.prop(s, "export_format", text="")
        row = layout.row(align=True)
        for target, text, icon in (("TEXT", "Text Editor", "TEXT"), ("CLIPBOARD", "Copy", "COPYDOWN"),
                                   ("FILE", "Save...", "FILE_TICK")):
            op = row.operator("ui_builder.export", text=text, icon=icon)
            op.format = s.export_format
            op.target = target
        if s.export_format == "LLM":
            layout.label(text="Paste into an LLM and describe behaviour.", icon="INFO")
        op = layout.operator("ui_builder.export", text="Save Project (JSON)", icon="EXPORT")
        op.format = "JSON"
        op.target = "FILE"


class UIB_PT_import(bpy.types.Panel):
    bl_label = "Import From Addon"
    bl_idname = "UIB_PT_import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s = settings(context)
        layout.label(text="Copy the UI of an enabled addon", icon="IMPORT")
        layout.prop(s, "import_module", text="")
        layout.prop(s, "import_mode", text="")
        layout.operator("ui_builder.scan_addon", icon="VIEWZOOM")
        if len(s.import_panels):
            box = layout.box()
            col = box.column(align=True)
            for p in s.import_panels:
                row = col.row(align=True)
                if p.parent_id:
                    row.label(text="", icon="BLANK1")
                row.prop(p, "include", text=p.label)
            row = layout.row()
            row.scale_y = 1.5
            row.operator("ui_builder.import_addon", icon="IMPORT")
        else:
            layout.label(text="Scan, tick panels, then import.")
            layout.operator("ui_builder.import_addon", text="Import All Panels", icon="IMPORT")


class UIB_PT_update(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "UIB_PT_update"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        prefs = preferences.get_prefs(context)
        if prefs:
            preferences.draw_update_box(self.layout, prefs, compact=True)


classes = (UIB_UL_elements, *[m for _, _, _, m in _add_menus], UIB_MT_add, UIB_MT_project,
           UIB_PT_main, UIB_PT_element, UIB_PT_export, UIB_PT_import, UIB_PT_update)
