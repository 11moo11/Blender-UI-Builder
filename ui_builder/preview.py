"""Live mockup: draws the element tree with real Blender UI widgets."""

import bpy

from . import elements as el
from . import tree
from .icons import valid_icon


class UIB_OT_mock_action(bpy.types.Operator):
    """Placeholder action used by mockup buttons"""
    bl_idname = "ui_builder.mock_action"
    bl_label = "Mock Button"

    name: bpy.props.StringProperty(options={"SKIP_SAVE"})
    tip: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.tip or "Mockup button (does nothing)"

    def execute(self, context):
        self.report({"INFO"}, "Mockup button: %s" % (self.name or "unnamed"))
        return {"FINISHED"}


class UIB_UL_mock(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        else:
            layout.alignment = "CENTER"
            layout.label(text="", icon_value=icon)


def _apply(layout, attrs):
    for name, value in attrs:
        try:
            setattr(layout, name, value)
        except (AttributeError, TypeError):
            pass


class Drawer:
    def __init__(self, settings):
        self.settings = settings

    # -- argument resolution -------------------------------------------------
    def _args(self, e, spec):
        out = []
        for a in spec.args:
            if isinstance(a, el.Ref):
                if a.kind == "value":
                    out += [e, el.value_attr(e)]
                elif a.kind == "items":
                    out += [self.settings, "mock_items"]
                else:
                    out += [self.settings, "mock_index"]
            elif isinstance(a, el.Sym):
                out.append(self._sym(e, a.name))
            else:
                out.append(a)
        return out

    def _sym(self, e, name):
        if name == "bpy.data":
            return bpy.data
        if name == "operator":
            return UIB_OT_mock_action.bl_idname
        if name == "uilist":
            return UIB_UL_mock.__name__
        if name == "value":
            return getattr(e, el.value_attr(e))
        raise KeyError(name)

    def call(self, layout, e, spec):
        args = self._args(e, spec)
        kwargs = {k: (self._sym(e, v.name) if isinstance(v, el.Sym) else v) for k, v in spec.kwargs.items()}
        method = getattr(layout, spec.method, None)
        if method is None:  # feature not available in this Blender version
            layout.label(text="%s (needs newer Blender)" % e.label, icon="ERROR")
            return
        try:
            result = method(*args, **kwargs)
        except TypeError:
            if spec.method != "separator":
                raise
            layout.separator()
            return
        if spec.method == "operator" and result is not None:
            result.name = e.label
            result.tip = e.description

    # -- tree ------------------------------------------------------------------
    def nodes(self, layout, nodes):
        for n in nodes:
            self.node(layout, n)

    def node(self, layout, n):
        e = n.elem
        d = el.DEFS.get(e.type)
        if d is None:
            return
        if e.type == "POPOVER":
            self.popover(layout, n)
        elif d.container:
            self.container(layout, n)
        else:
            target = layout
            attrs = el.layout_attrs(e, False)
            if attrs:
                target = layout.row(align=True)
                _apply(target, attrs)
            for spec in el.leaf_specs(e):
                self.call(target, e, spec)

    def _header(self, layout, e, checkbox=False):
        row = layout.row(align=True)
        icon = "TRIA_DOWN" if e.expanded else "TRIA_RIGHT"
        row.prop(e, "expanded", text=e.label, icon=icon, emboss=False)
        if checkbox:
            row.prop(e, "bool_value", text="")
        return row

    def container(self, layout, n):
        e = n.elem
        attrs = el.layout_attrs(e, True)
        if e.type in ("PANEL", "COLLAPSE"):
            box = layout.box()
            self._header(box, e, e.type == "PANEL" and e.header_checkbox)
            if e.expanded:
                body = box.column()
                _apply(body, attrs)
                if e.type == "PANEL" and e.header_checkbox and not e.bool_value:
                    body.active = False
                self.nodes(body, n.children)
            return
        method, kw = el.container_spec(e)
        sub = getattr(layout, method)(**kw)
        _apply(sub, attrs)
        self.nodes(sub, n.children)

    def popover(self, layout, n):
        e = n.elem
        attrs = el.layout_attrs(e, False)
        target = layout
        if attrs:
            target = layout.row(align=True)
            _apply(target, attrs)
        kw = {"text": e.label, "toggle": True}
        icon = valid_icon(e.icon)
        if icon:
            kw["icon"] = icon
        target.prop(e, "expanded", **kw)
        if e.expanded:
            box = layout.box()
            box.label(text="Popover contents", icon="FULLSCREEN_ENTER")
            self.nodes(box.column(), n.children)


def draw_preview(layout, context):
    s = context.scene.ui_builder
    roots = tree.build(s.elements)
    if not roots:
        layout.label(text="Nothing to preview yet.", icon="INFO")
        layout.label(text="Add elements in the 'UI Builder' tab.")
        return
    Drawer(s).nodes(layout, roots)


class UIB_PT_preview_view3d(bpy.types.Panel):
    bl_label = "Mockup Preview"
    bl_idname = "UIB_PT_preview_view3d"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mockup"

    def draw(self, context):
        draw_preview(self.layout, context)


class UIB_PT_preview_props(bpy.types.Panel):
    bl_label = "UI Builder Mockup"
    bl_idname = "UIB_PT_preview_props"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        draw_preview(self.layout, context)


classes = (UIB_OT_mock_action, UIB_UL_mock, UIB_PT_preview_view3d, UIB_PT_preview_props)
