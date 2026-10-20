"""The builder interface (3D Viewport sidebar > UI Builder tab)."""

import bpy

from . import elements as el
from . import icons, import_ops, locmap, preferences, updater
from .properties import settings


def importer_prefix(kind):
    from .importer import KIND_PREFIX
    return KIND_PREFIX[kind].replace(": ", " - ") if kind != "PANEL" else ""


def _under_hidden(elems, index):
    """True if an ancestor of element `index` is hidden."""
    indent = elems[index].indent
    for k in range(index - 1, -1, -1):
        if elems[k].indent < indent:
            if elems[k].hide:
                return True
            indent = elems[k].indent
            if indent == 0:
                break
    return False


class UIB_UL_elements(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        d = el.DEFS.get(item.type)
        elems = data.elements
        row = layout.row(align=True)
        hidden = item.hide or _under_hidden(elems, index)
        row.active = not hidden  # greyed like a hidden object in the Outliner
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
        else:
            row.label(text="", icon=d.icon if d else "QUESTION")
            row.prop(item, "label", text="", emboss=False)
            if d:
                sub = row.row()
                sub.enabled = False
                sub.label(text=d.label)
        row.prop(item, "hide", text="", emboss=False, icon="HIDE_ON" if item.hide else "HIDE_OFF")

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
        l.separator()
        l.operator("ui_builder.visibility", text="Show All in Mockup", icon="HIDE_OFF").action = "SHOW_ALL"


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

        view = layout.row(align=True)
        view.operator("ui_builder.mockup_split", text="Mockup Beside", icon="SPLIT_VERTICAL").direction = "VERTICAL"
        view.operator("ui_builder.mockup_window", text="Mockup Window", icon="WINDOW")
        row = layout.row()
        row.template_list("UIB_UL_elements", "", s, "elements", s, "active_index", rows=8)
        col = row.column(align=True)
        col.menu("UIB_MT_select", icon="RESTRICT_SELECT_OFF", text="")
        col.separator()
        col.operator("ui_builder.visibility", icon="HIDE_OFF", text="").action = "TOGGLE"
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


_TYPE_PROPS = {"ENUM": "enum_style", "BOOL": "bool_style", "SEPARATOR": "separator_style",
               "PROGRESS": "progress_type"}  # the "Type" selector, shown first


def draw_element(layout, e):
    d = el.DEFS[e.type]
    t = e.type
    layout.use_property_split = False
    if t == "OPTION":
        box = layout.box()
        box.label(text="Option: %s" % e.label, icon="RIGHTARROW_THIN")
        for line in ("Everything inside this row is shown only", "while this option is selected.",
                     "Rename or reorder options in the Choice's", "Selectables field."):
            box.label(text=line)
        _pick_icon(layout.column(), e)  # the icon is used on the Choice's buttons / dropdown entries
        return

    # header: big Pick Icon button next to the element type
    head = layout.row()
    if d.icon_ok:
        pick = head.row(align=True)
        pick.scale_y = 2.14
        _pick_icon(pick, e)
    title = head.row(align=True)
    title.scale_x = 2.0
    title.alignment = "LEFT"
    title.label(text=d.label, icon=d.icon)
    if t in _TYPE_PROPS:
        layout.prop(e, _TYPE_PROPS[t], text="Type")
    try:
        layout.separator(type="LINE", factor=2.62)
    except TypeError:  # older Blender without separator types
        layout.separator()

    # identity
    layout.prop(e, "label", text="Name")
    if d.ident:
        row = layout.row(align=True)
        row.prop(e, "ident", text="ID")
        row.prop(e, "auto_ident", text="", icon="LINKED" if e.auto_ident else "UNLINKED", toggle=True)
    if d.desc:
        layout.prop(e, "description", text="Tooltip")

    # what is specific to this element type. Every on/off option is collected into one grid below.
    flags = []  # (property, label or None)
    if t == "TEXT_LINES":
        layout.label(text="Separate lines with |  in the name")
    elif t == "PANEL":
        flags += [("default_closed", None), ("header_checkbox", None)]
    elif t in ("ROW", "COLUMN", "SPLIT", "GRID"):
        flags.append(("align", "Connect Items"))
        if t == "SPLIT":
            layout.prop(e, "split_factor")
        if t == "GRID":
            layout.prop(e, "grid_columns")
            flags += [("grid_row_major", None), ("grid_even_columns", None), ("grid_even_rows", None)]
    elif t == "SPACER":
        layout.prop(e, "spacer_factor")
    elif t == "BOOL":
        layout.prop(e, "bool_value", text="Default Value")
    elif t in ("INT", "FLOAT", "SLIDER", "FACTOR", "PERCENT", "ANGLE", "DISTANCE", "STRING", "FILEPATH",
               "DIRPATH", "COLOR", "COLOR_ALPHA", "VEC2", "VEC3", "EULER", "SEARCH", "PROGRESS"):
        layout.prop(e, el.value_attr(e), text="Default Value")
        if t == "COLOR":
            flags.append(("use_alpha", None))
        if t == "SEARCH":
            layout.prop(e, "search_source")
        if t in ("INT", "FLOAT", "SLIDER", "FACTOR", "PERCENT", "ANGLE", "DISTANCE"):
            flags.append(("use_range", None))
            if e.use_range:
                r = layout.row(align=True)
                r.prop(e, "range_min")
                r.prop(e, "range_max")
    elif t in ("ENUM", "MENU"):
        layout.prop(e, "enum_items", text="Selectables")
        if "PLACEHOLDER_" in e.enum_items:
            warn = layout.box()
            warn.alert = True
            warn.label(text="Placeholder options: the real ones", icon="ERROR")
            warn.label(text="could not be read. Replace them.")
        if t == "ENUM" and e.enum_style != "DROPDOWN":
            flags.append(("enum_icon_only", None))
        layout.prop(e, "enum_value", text="Default Value")
    elif t in ("POINTER", "TEMPLATE_ID"):
        layout.prop(e, "id_type")
    elif t == "LIST":
        layout.prop(e, "list_rows")
    elif t == "IMAGE_PREVIEW":
        layout.prop(e, "preview_scale")
    elif t == "BUTTON":
        layout.label(text="Exports an operator stub", icon="INFO")

    # layout modifiers
    box = layout.box()
    col = box.column(align=True)
    grid = col.grid_flow(row_major=True, even_columns=True, even_rows=True)
    flags.append(("enabled", None))
    if t not in ("SEPARATOR", "SPACER"):
        flags.append(("alert", None))
    if t in el.SPLIT_TYPES:
        flags.append(("prop_split", "Show Name on Left"))
    elif d.container and t not in ("POPOVER", "OPTION"):
        flags.append(("prop_split", "Property Split (children)"))
    for prop, text in flags:
        if text:
            grid.prop(e, prop, text=text)
        else:
            grid.prop(e, prop)
    col.prop(e, "scale_x")
    col.prop(e, "scale_y")
    if t not in ("SEPARATOR", "SPACER"):
        col.prop(e, "emboss")
    col.prop(e, "alignment")

    if t == "ENUM":
        info = layout.box()
        info.label(text="Each option has its own row in the list.", icon="INFO")
        info.label(text="Put controls under an option to show")
        info.label(text="them only when it is chosen. Give an option")
        info.label(text="an icon for icon buttons.")


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
            layout.prop(s, "import_explore")
            box = layout.box()
            col = box.column(align=True)
            for kind, cls, included in panels:
                row = col.row(align=True)
                if kind == "PANEL" and getattr(cls, "bl_parent_id", ""):
                    row.label(text="", icon="BLANK1")
                name = (getattr(cls, "bl_label", "") or cls.__name__)
                op = row.operator("ui_builder.toggle_import_panel", text=importer_prefix(kind) + name,
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
