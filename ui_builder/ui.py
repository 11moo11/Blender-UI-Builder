"""The builder interface (3D Viewport sidebar > UI Builder tab)."""

import bpy

from . import elements as el
from . import icons, import_ops, locmap, preferences, updater
from .properties import settings


class UIB_UL_elements(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        d = el.DEFS.get(item.type)
        elems = data.elements
        row = layout.row(align=True)
        row.prop(item, "selected", text="", emboss=False,
                 icon="CHECKBOX_HLT" if item.selected else "CHECKBOX_DEHLT")
        for _ in range(item.indent):
            row.label(text="", icon="BLANK1")
        if index + 1 < len(elems) and elems[index + 1].indent > item.indent:
            row.prop(item, "fold", text="", emboss=False, icon="TRIA_RIGHT" if item.fold else "TRIA_DOWN")
        else:
            row.label(text="", icon="BLANK1")
        if item.type == "OPTION":  # label comes from the Choice's option list, so it is not editable here
            row.label(text="If: %s" % item.label, icon=icons.valid_icon(item.icon) or "RIGHTARROW_THIN")
            sub = row.row()
            sub.enabled = False
            sub.label(text="Option")
            return
        row.label(text="", icon=d.icon if d else "QUESTION")
        row.prop(item, "label", text="", emboss=False)
        if d:
            sub = row.row()
            sub.enabled = False
            sub.label(text=d.label)

    def filter_items(self, context, data, propname):
        """Hide the children of folded elements."""
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item] * len(items)
        hide_below = None
        for i, e in enumerate(items):
            if hide_below is not None and e.indent > hide_below:
                flags[i] = 0
                continue
            hide_below = e.indent if e.fold else None
        return flags, []


def _add_menu(category, title, icon, operator="ui_builder.add", prefix="add"):
    ns = {"bl_label": title}

    def draw(self, context):
        for d in el.defs_in(category):
            op = self.layout.operator(operator, text=d.label, icon=d.icon)
            op.type = d.id
        if category == "LAYOUT" and operator == "ui_builder.add":
            op = self.layout.operator("ui_builder.add", text="Sub-panel", icon="WINDOW")
            op.type = "SUBPANEL"

    ns["draw"] = draw
    return type("UIB_MT_%s_%s" % (prefix, category.lower()), (bpy.types.Menu,), ns)


_add_menus = [(c, t, i, _add_menu(c, t, i)) for c, t, i in el.CATEGORIES]
_replace_menus = [(c, t, i, _add_menu(c, t, i, "ui_builder.replace", "replace")) for c, t, i in el.CATEGORIES]


class UIB_MT_add(bpy.types.Menu):
    bl_label = "Add Element"

    def draw(self, context):
        for category, title, icon, menu in _add_menus:
            self.layout.menu(menu.__name__, text=title, icon=icon)


class UIB_MT_replace(bpy.types.Menu):
    bl_label = "Replace Selected"

    def draw(self, context):
        for category, title, icon, menu in _replace_menus:
            self.layout.menu(menu.__name__, text=title, icon=icon)


class UIB_MT_select(bpy.types.Menu):
    bl_label = "Select"

    def draw(self, context):
        l = self.layout
        for action, text, icon in (("ALL", "All", "CHECKBOX_HLT"), ("NONE", "None", "CHECKBOX_DEHLT"),
                                   ("INVERT", "Invert", "ARROW_LEFTRIGHT"), ("CHILDREN", "Add Children", "OUTLINER"),
                                   ("SIBLINGS", "Same Level", "ALIGN_JUSTIFY")):
            l.operator("ui_builder.select", text=text, icon=icon).action = action


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
                box.operator("ui_builder.restart_blender", icon="QUIT")

        row = layout.row()
        row.template_list("UIB_UL_elements", "", s, "elements", s, "active_index", rows=8)
        col = row.column(align=True)
        col.menu("UIB_MT_select", icon="RESTRICT_SELECT_OFF", text="")
        col.separator()
        col.operator("ui_builder.remove", icon="REMOVE", text="")
        col.operator("ui_builder.duplicate", icon="DUPLICATE", text="")
        col.separator()
        col.operator("ui_builder.move", icon="TRIA_UP", text="").direction = "UP"
        col.operator("ui_builder.move", icon="TRIA_DOWN", text="").direction = "DOWN"
        col.separator()
        col.operator("ui_builder.indent", icon="FORWARD", text="").direction = "IN"
        col.operator("ui_builder.indent", icon="BACK", text="").direction = "OUT"
        big = layout.row(align=True)
        big.scale_y = 2.0
        big.menu("UIB_MT_add", text="Add Element", icon="ADD")
        rep = big.row(align=True)
        rep.enabled = len(s.elements) > 0
        rep.menu("UIB_MT_replace", text="Replace Selected", icon="FILE_REFRESH")
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


def draw_element(layout, e):
    d = el.DEFS[e.type]
    t = e.type
    layout.use_property_split = False
    if t == "OPTION":
        box = layout.box()
        box.label(text="Option: %s" % e.label, icon="RIGHTARROW_THIN")
        for line in ("Everything inside this row is shown only", "while this option is selected.",
                     "Rename or reorder options in the Choice's", "Options field."):
            box.label(text=line)
        _pick_icon(layout.column(), e)  # the icon is used on the Choice's buttons / dropdown entries
        return
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
        if t == "COLOR":
            col.prop(e, "use_alpha")
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
        if "PLACEHOLDER_" in e.enum_items:
            warn = col.box()
            warn.alert = True
            warn.label(text="Placeholder options: the real ones", icon="ERROR")
            warn.label(text="could not be read. Replace them.")
        if t == "ENUM":
            col.prop(e, "enum_style")
            if e.enum_style != "DROPDOWN":
                col.prop(e, "enum_icon_only")
            box = col.box()
            box.label(text="Each option has its own row in the list.", icon="INFO")
            box.label(text="Put controls under an option to show")
            box.label(text="them only when it is chosen. Give an option")
            box.label(text="an icon for icon buttons.")
        col.prop(e, "enum_value", text="Default")
    elif t in ("POINTER", "TEMPLATE_ID"):
        col.prop(e, "id_type")
    elif t == "LIST":
        col.prop(e, "list_rows")
    elif t == "IMAGE_PREVIEW":
        col.prop(e, "preview_scale")
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
    if t in el.SPLIT_TYPES:
        m.prop(e, "prop_split", text="Label on the Left")
    elif d.container and t not in ("POPOVER", "OPTION"):
        m.prop(e, "prop_split", text="Property Split (children)")


class UIB_PT_location(bpy.types.Panel):
    bl_label = "Where It Lives"
    bl_idname = "UIB_PT_location"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Builder"

    def draw(self, context):
        layout = self.layout
        s = settings(context)
        entries, selected, node = locmap.entries(s)
        if not entries:
            layout.label(text="Add elements to see where they live.", icon="INFO")
            return
        locmap.draw_overview(layout, s, entries, selected)
        row = layout.row()
        row.label(text="Blue: used by the project", icon="DOT")
        row.label(text="Red: selected")

        if node is not None:
            e = node.elem
            box = layout.box()
            box.label(text="Selected: %s" % (e.label or el.DEFS[e.type].label), icon=el.DEFS[e.type].icon)
            if e.type == "PANEL" and node.is_panel and node.parent is None:
                box.prop(e, "panel_placement", text="")
                if e.panel_placement == "CUSTOM":
                    col = box.column(align=True)
                    col.prop(e, "p_space")
                    col.prop(e, "p_region")
                    col.prop(e, "p_context")
                if e.panel_placement != "PROJECT":
                    box.prop(e, "p_category")
                    box.prop(e, "p_parent")
            elif e.type == "PANEL":
                box.label(text="Sub-panel: shown inside its parent panel.")
            elif node.outside is not None and node.outside is not node:
                box.label(text="Follows its container's location.")
            else:
                box.prop(e, "location", text="")
                if e.location != "PANEL":
                    box.prop(e, "location_note")
                else:
                    box.label(text="Drawn by its panel. Change this if it lives elsewhere", icon="INFO")
        if selected is not None:
            layout.separator()
            wrap_label = locmap.wrap_label
            wrap_label(layout, selected.title, icon="WINDOW")
            if selected.space:
                locmap.draw_detail(layout, s, selected)

        box = layout.box()
        box.label(text="Everything", icon="OUTLINER")
        for entry in entries:
            locmap.wrap_label(box, "%s: %s" % (entry.label, entry.title), width=36, icon="DOT")


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
        panels = import_ops.listed_panels(s) if s.import_module != "NONE" else []
        if panels:
            box = layout.box()
            col = box.column(align=True)
            for cls, included in panels:
                row = col.row(align=True)
                if getattr(cls, "bl_parent_id", ""):
                    row.label(text="", icon="BLANK1")
                op = row.operator("ui_builder.toggle_import_panel", text=getattr(cls, "bl_label", "") or cls.__name__,
                                  icon="CHECKBOX_HLT" if included else "CHECKBOX_DEHLT", emboss=False)
                op.idname = import_ops.panel_id(cls)
            row = layout.row()
            row.scale_y = 1.5
            row.operator("ui_builder.import_addon", icon="IMPORT")
        else:
            layout.label(text="Enable an addon that has panels first.", icon="INFO")


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


classes = (UIB_UL_elements, *[m for _, _, _, m in _add_menus], *[m for _, _, _, m in _replace_menus],
           UIB_MT_add, UIB_MT_replace, UIB_MT_select, UIB_MT_project,
           UIB_PT_main, UIB_PT_element, UIB_PT_location, UIB_PT_export, UIB_PT_import, UIB_PT_update)
