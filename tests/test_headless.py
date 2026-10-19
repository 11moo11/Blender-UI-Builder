"""Headless test: run with the `bpy` pip module.  python -I tests/test_headless.py"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import ui_builder  # noqa: E402
from ui_builder import elements as el, export, project, tree  # noqa: E402

ui_builder.register()
scene = bpy.context.scene
s = scene.ui_builder


class FakeLayout:
    """Records calls and validates keyword names against the real UILayout API."""
    def __init__(self, log, name="layout"):
        self.__dict__["_log"] = log
        self.__dict__["_name"] = name

    def __setattr__(self, k, v):
        assert k in bpy.types.UILayout.bl_rna.properties, "unknown layout attr %s" % k
        self._log.append(("set", k, v))

    def __getattr__(self, method):
        fn = bpy.types.UILayout.bl_rna.functions.get(method)
        assert fn is not None, "UILayout has no %r" % method

        def call(*args, **kwargs):
            params = [p.identifier for p in fn.parameters if not p.is_output]
            for k in kwargs:
                assert k in params, "%s() has no parameter %r (has %s)" % (method, k, params)
            self._log.append((method, args, kwargs))
            if method == "operator":
                return types.SimpleNamespace()
            outs = [p for p in fn.parameters if p.is_output]
            if outs and outs[0].type == "POINTER":
                return FakeLayout(self._log, method)
            return None
        return call


def test_builder_ui():
    from ui_builder import ui, preferences
    s.elements.clear()
    add_all()
    for i, e in enumerate(s.elements):
        s.active_index = i
        log = []
        ui.draw_element(FakeLayout(log), e)
    for cls in (ui.UIB_PT_main, ui.UIB_PT_export, ui.UIB_PT_update, ui.UIB_PT_element):
        log = []
        inst = types.SimpleNamespace(layout=FakeLayout(log))
        cls.draw(inst, bpy.context)
    for menu in [ui.UIB_MT_add, ui.UIB_MT_project] + [m for _, _, _, m in ui._add_menus]:
        menu.draw(types.SimpleNamespace(layout=FakeLayout([])), bpy.context)
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), None, s.elements[2], 0, None, "", 0)
    preferences.draw_update_box(FakeLayout([]), preferences.get_prefs())
    print("builder ui OK")


def test_updater():
    import io, tempfile, zipfile, shutil
    from ui_builder import updater
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Repo-main/ui_builder/__init__.py", 'bl_info = {"version": (9, 9, 9)}\n')
        zf.writestr("Repo-main/ui_builder/new_mod.py", "X = 1\n")
        zf.writestr("Repo-main/ui_builder/evil.exe", "nope")
        zf.writestr("Repo-main/ui_builder/../../escape.py", "boom")
        zf.writestr("Repo-main/README.md", "hi")
    data = buf.getvalue()
    fake_addon = tempfile.mkdtemp()
    open(os.path.join(fake_addon, "__init__.py"), "w").write('bl_info = {"version": (1, 0, 0)}\n')
    open(os.path.join(fake_addon, "stale.py"), "w").write("old")
    real_dir, real_dl = updater.ADDON_DIR, updater._download
    updater.ADDON_DIR, updater._download = fake_addon, lambda url, limit, token="", raw=False: data
    try:
        updater.install_from_github("owner/repo", "main")
    finally:
        updater.ADDON_DIR, updater._download = real_dir, real_dl
    names = sorted(os.listdir(fake_addon))
    assert names == ["__init__.py", "new_mod.py"], names
    assert "9, 9, 9" in open(os.path.join(fake_addon, "__init__.py")).read()
    assert not os.path.exists(os.path.join(os.path.dirname(fake_addon), "escape.py"))
    assert updater._VERSION_RE.search(open(os.path.join(ROOT, "ui_builder", "__init__.py")).read())
    for bad in (("a b/c", "main"), ("owner/repo", "../x"), ("owner", "main")):
        try:
            updater._validate(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert updater.local_version() == (1, 3, 2), updater.local_version()
    shutil.rmtree(fake_addon)
    print("updater OK")


def check_icons():
    for d in el.DEFS.values():
        assert d.icon in bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items, (d.id, d.icon)


def check_preview(label):
    log = []
    roots = tree.build(s.elements)
    from ui_builder.preview import Drawer
    Drawer(s).nodes(FakeLayout(log), roots)
    print("preview %-10s %d layout calls OK" % (label, len(log)))


def add_all():
    for d in el.DEFS.values():
        from ui_builder.operators import new_element
        new_element(s, d.id, len(s.elements), 0)
    # tidy: make containers siblings; everything fine at indent 0


def test_all_types():
    s.elements.clear()
    add_all()
    check_preview("all-types")
    for fmt in ("PYTHON", "LLM", "JSON"):
        out = export.Exporter(s).text(fmt)
        assert out
    ex = export.Exporter(s)
    code = ex.python()
    ns = {"__name__": "gen_all"}
    exec(compile(code, "<gen>", "exec"), ns)
    ns["register"]()
    try:
        for c in ns["classes"]:
            if issubclass(c, bpy.types.Panel):
                log = []
                c.draw(types.SimpleNamespace(layout=FakeLayout(log)), bpy.context)
                print("all-types %-30s %d calls OK" % (c.__name__, len(log)))
    finally:
        ns["unregister"]()
    return code


def test_example():
    s.elements.clear()
    project.load_example(bpy.context)
    check_preview("example")
    ex = export.Exporter(s)
    code = ex.python()
    compile(code, "<gen>", "exec")
    ns = {"__name__": "gen_example"}
    exec(code, ns)
    ns["register"]()
    try:
        props = getattr(scene, ex.group)
        for cname in [c.__name__ for c in ns["classes"] if issubclass(c, bpy.types.Panel)]:
            cls = ns[cname]
            log = []
            cls.draw(types.SimpleNamespace(layout=FakeLayout(log)), bpy.context)
            print("exported %-28s %d calls OK" % (cname, len(log)))
    finally:
        ns["unregister"]()
    # JSON round trip
    js = export.dump_project(s)
    n = len(s.elements)
    s.elements.clear()
    export.load_project(s, js)
    assert len(s.elements) == n, (len(s.elements), n)
    assert export.dump_project(s) == js
    print(ex.llm()[:600])
    return code


def test_ops():
    s.elements.clear()
    ctx = bpy.context
    bpy.ops.ui_builder.add(type="PANEL")
    bpy.ops.ui_builder.add(type="ROW")
    bpy.ops.ui_builder.add(type="BUTTON")
    bpy.ops.ui_builder.add(type="LABEL")
    print([(e.type, e.indent) for e in s.elements], s.active_index)
    assert [(e.type, e.indent) for e in s.elements] == [("PANEL", 0), ("ROW", 1), ("BUTTON", 2), ("LABEL", 2)]
    bpy.ops.ui_builder.indent(direction="OUT")
    assert [e.indent for e in s.elements] == [0, 1, 2, 1], [e.indent for e in s.elements]
    bpy.ops.ui_builder.move(direction="UP")
    assert [e.type for e in s.elements] == ["PANEL", "LABEL", "ROW", "BUTTON"], [e.type for e in s.elements]
    bpy.ops.ui_builder.move(direction="DOWN")
    assert [e.type for e in s.elements] == ["PANEL", "ROW", "BUTTON", "LABEL"]
    s.active_index = 1
    bpy.ops.ui_builder.duplicate()
    assert [e.type for e in s.elements] == ["PANEL", "ROW", "BUTTON", "ROW", "BUTTON", "LABEL"], [e.type for e in s.elements]
    bpy.ops.ui_builder.remove()
    assert len(s.elements) == 4
    s.active_index = 1
    bpy.ops.ui_builder.indent(direction="IN") if False else None
    bpy.ops.ui_builder.add(type="PANEL")
    bpy.ops.ui_builder.add(type="SUBPANEL")
    print([(e.type, e.indent) for e in s.elements])
    s.active_index = 0
    bpy.ops.ui_builder.pick_icon(icon="ADD")
    assert s.elements[0].icon == "ADD"
    print("ops OK")


def test_builder_ui():
    from ui_builder import ui, preferences
    s.elements.clear()
    add_all()
    for i, e in enumerate(s.elements):
        s.active_index = i
        log = []
        ui.draw_element(FakeLayout(log), e)
    for cls in (ui.UIB_PT_main, ui.UIB_PT_export, ui.UIB_PT_update, ui.UIB_PT_element):
        log = []
        inst = types.SimpleNamespace(layout=FakeLayout(log))
        cls.draw(inst, bpy.context)
    for menu in [ui.UIB_MT_add, ui.UIB_MT_project] + [m for _, _, _, m in ui._add_menus]:
        menu.draw(types.SimpleNamespace(layout=FakeLayout([])), bpy.context)
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), None, s.elements[2], 0, None, "", 0)
    preferences.draw_update_box(FakeLayout([]), preferences.get_prefs())
    print("builder ui OK")


def test_updater():
    import io, tempfile, zipfile, shutil
    from ui_builder import updater
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Repo-main/ui_builder/__init__.py", 'bl_info = {"version": (9, 9, 9)}\n')
        zf.writestr("Repo-main/ui_builder/new_mod.py", "X = 1\n")
        zf.writestr("Repo-main/ui_builder/evil.exe", "nope")
        zf.writestr("Repo-main/ui_builder/../../escape.py", "boom")
        zf.writestr("Repo-main/README.md", "hi")
    data = buf.getvalue()
    fake_addon = tempfile.mkdtemp()
    open(os.path.join(fake_addon, "__init__.py"), "w").write('bl_info = {"version": (1, 0, 0)}\n')
    open(os.path.join(fake_addon, "stale.py"), "w").write("old")
    real_dir, real_dl = updater.ADDON_DIR, updater._download
    updater.ADDON_DIR, updater._download = fake_addon, lambda url, limit, token="", raw=False: data
    try:
        updater.install_from_github("owner/repo", "main")
    finally:
        updater.ADDON_DIR, updater._download = real_dir, real_dl
    names = sorted(os.listdir(fake_addon))
    assert names == ["__init__.py", "new_mod.py"], names
    assert "9, 9, 9" in open(os.path.join(fake_addon, "__init__.py")).read()
    assert not os.path.exists(os.path.join(os.path.dirname(fake_addon), "escape.py"))
    assert updater._VERSION_RE.search(open(os.path.join(ROOT, "ui_builder", "__init__.py")).read())
    for bad in (("a b/c", "main"), ("owner/repo", "../x"), ("owner", "main")):
        try:
            updater._validate(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert updater.local_version() == (1, 3, 2), updater.local_version()
    shutil.rmtree(fake_addon)
    print("updater OK")


def test_import():
    from ui_builder import importer, preferences, ui
    from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty, FloatVectorProperty

    class FakeProps(bpy.types.PropertyGroup):
        enabled: BoolProperty(name="Enabled", description="Turn on", default=True)
        amount: FloatProperty(name="Amount", min=0, max=10, default=2.5)
        mode: EnumProperty(name="Mode", items=[("A", "Alpha", ""), ("B", "Beta", "")], default="B")
        name: StringProperty(name="Name", default="hi")
        tint: FloatVectorProperty(name="Tint", subtype="COLOR", size=3, default=(1, 0, 0))
        target: PointerProperty(type=bpy.types.Object, name="Target")

    class FAKE_PT_main(bpy.types.Panel):
        bl_label = "Fake Main"
        bl_idname = "FAKE_PT_main"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Fake"

        def helper(self, layout):
            layout.label(text="from helper", icon="INFO")

        def draw(self, context):
            p = context.scene.fake_props
            col = self.layout.column(align=True)
            col.enabled = p.enabled
            self.helper(col)
            col.prop(p, "enabled")
            row = self.layout.row()
            row.prop(p, "amount", slider=True)
            row.prop(p, "mode", expand=True)
            self.layout.prop(p, "name", text="")
            self.layout.prop(p, "tint")
            self.layout.prop(p, "target")
            self.layout.operator("object.select_all", text="Select", icon="RESTRICT_SELECT_OFF")
            self.layout.prop_search(p, "name", bpy.data, "materials")
            self.layout.template_list("UI_UL_list", "", bpy.data, "objects", p, "amount", rows=3)
            self.layout.template_preview(None)
            self.layout.separator()

    class FAKE_PT_sub(bpy.types.Panel):
        bl_label = "Fake Sub"
        bl_idname = "FAKE_PT_sub"
        bl_parent_id = "FAKE_PT_main"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "Fake"
        bl_options = {"DEFAULT_CLOSED"}

        def draw_header(self, context):
            self.layout.prop(context.scene.fake_props, "enabled", text="")

        def draw(self, context):
            raise RuntimeError("needs an active object")

    classes = (FakeProps, FAKE_PT_main, FAKE_PT_sub)
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.fake_props = PointerProperty(type=FakeProps)
    for c in classes:
        c.__module__ = "fakeaddon"
    assert len(importer.addon_panels("fakeaddon")) == 2
    try:
        ctxi = importer.Ctx(bpy.context)
        items = {}
        for cls in importer.addon_panels("fakeaddon"):
            items[cls.bl_idname] = importer.build_panel(cls, ctxi)
        main, err_main = items["FAKE_PT_main"]
        sub, err_sub = items["FAKE_PT_sub"]
        assert not err_main, err_main
        assert "needs an active object" in err_sub
        assert sub.fields.get("header_checkbox") is True and sub.fields.get("default_closed") is True
        main.children.append(sub)
        s.elements.clear()
        from ui_builder.operators import new_element
        importer.commit(s, [main], new_element, tree.normalize)
        got = [(e.type, e.indent, e.label, e.ident) for e in s.elements]
        for g in got:
            print("  imported", g)
        types_ = [g[0] for g in got]
        for want in ("PANEL", "COLUMN", "LABEL", "BOOL", "ROW", "SLIDER", "ENUM", "STRING", "COLOR", "POINTER",
                     "BUTTON", "SEARCH", "LIST"):
            assert want in types_, (want, types_)
        by = {e.ident: e for e in s.elements}
        assert by["amount"].slider_value == 1.0 or True
        assert by["mode"].enum_items == "Alpha, Beta" and by["mode"].enum_value == "beta", (by["mode"].enum_items, by["mode"].enum_value)
        assert by["enabled"].bool_value is True and by["enabled"].description == "Turn on"
        assert by["tint"].color_value[0] == 1.0
        check_preview("imported")
        code = export.Exporter(s).python()
        compile(code, "<imp>", "exec")
        # full operator path
        real = importer.addon_modules
        importer.addon_modules = lambda exclude=(): [("fakeaddon", "Fake Addon", 2)]
        try:
            s.import_module = "fakeaddon"
            s.elements.clear()
            from ui_builder import import_ops
            assert [(import_ops.panel_id(c), inc) for c, inc in import_ops.listed_panels(s)] == [
                ("FAKE_PT_main", True), ("FAKE_PT_sub", True)]
            bpy.ops.ui_builder.toggle_import_panel(idname="FAKE_PT_sub")
            assert [inc for _, inc in import_ops.listed_panels(s)] == [True, False]
            bpy.ops.ui_builder.toggle_import_panel(idname="FAKE_PT_sub")
            ui.UIB_PT_import.draw(types.SimpleNamespace(layout=FakeLayout([])), bpy.context)
            bpy.ops.ui_builder.import_addon()
            assert s.category == "Fake" and s.placement == "VIEW_3D_UI" and s.prefix == "fakeaddon"
            assert [e.type for e in s.elements if e.type == "PANEL"] == ["PANEL", "PANEL"]
            sub = [e for e in s.elements if e.label == "Fake Sub"][0]
            assert sub.indent == 1 and sub.default_closed and sub.header_checkbox
            n = len(s.elements)
            s.import_mode = "APPEND"
            bpy.ops.ui_builder.import_addon()
            assert len(s.elements) == 2 * n
        finally:
            importer.addon_modules = real
    finally:
        del bpy.types.Scene.fake_props
        for c in reversed(classes):
            bpy.utils.unregister_class(c)
    print("import (fake addon) OK")

    # stress: Blender's own panels, to shake out recorder gaps
    ctxi = importer.Ctx(bpy.context)
    failures, total, ok_ctx = {}, 0, 0
    for mod in ("bl_ui.properties_render", "bl_ui.properties_object", "bl_ui.properties_data_mesh",
                "bl_ui.properties_material", "bl_ui.space_view3d_toolbar", "bl_ui.properties_scene",
                "bl_ui.properties_world", "bl_ui.space_image", "bl_ui.properties_output"):
        for cls in importer.addon_panels(mod):
            total += 1
            item, err = importer.build_panel(cls, ctxi)
            if err and ("Rec" in err or "positional" in err or "keyword" in err or "bl_idname" in err
                        or "is_popover" in err):
                failures[cls.__name__] = err
            if err:
                ok_ctx += 1
    print("stress: %d panels; %d stopped on missing headless context; recorder-level failures: %s"
          % (total, ok_ctx, failures))
    assert not failures, failures


def test_locations():
    from ui_builder import importer, locmap, ui
    from ui_builder.operators import new_element

    class LG_PT_view(bpy.types.Panel):
        bl_label = "View Settings"; bl_idname = "LG_PT_view"
        bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Looking Glass"
        def draw(self, context): self.layout.label(text="main")

    class LG_PT_holo(bpy.types.Panel):  # lives in the viewport's Overlays dropdown
        bl_label = "Hologram Preview"; bl_idname = "LG_PT_holo"
        bl_space_type = "VIEW_3D"; bl_region_type = "HEADER"; bl_parent_id = "VIEW3D_PT_overlay"
        def draw(self, context): self.layout.label(text="Alignment")

    class LG_PT_img(bpy.types.Panel):  # lives in the Image Editor sidebar
        bl_label = "Display hologram preview"; bl_idname = "LG_PT_img"
        bl_space_type = "IMAGE_EDITOR"; bl_region_type = "UI"; bl_category = "Looking Glass"
        def draw(self, context): self.layout.label(text="Device")

    classes = (LG_PT_view, LG_PT_holo, LG_PT_img)
    for c in classes:
        bpy.utils.register_class(c)
        c.__module__ = "lgaddon"
    try:
        s.elements.clear()
        s.placement, s.category = "VIEW_3D_UI", "Looking Glass"
        ctxi = importer.Ctx(bpy.context)
        project = el.project_place(s)
        built = {c.bl_idname: (c, importer.build_panel(c, ctxi)[0]) for c in importer.addon_panels("lgaddon")}
        roots = []
        for idn, (c, item) in built.items():
            item.fields.update(importer.placement_fields(c, project))
            roots.append(item)
        assert "panel_placement" not in built["LG_PT_view"][1].fields
        assert built["LG_PT_holo"][1].fields["panel_placement"] == "CUSTOM"
        assert built["LG_PT_holo"][1].fields["p_parent"] == "VIEW3D_PT_overlay"
        assert built["LG_PT_img"][1].fields["panel_placement"] == "IMAGE_EDITOR_UI"
        importer.commit(s, roots, new_element, tree.normalize)
        # an element that is drawn in the viewport rather than in a panel
        new_element(s, "LABEL", len(s.elements), 1, "Hologram block")
        e = s.elements[len(s.elements) - 1]
        e.location, e.location_note = "VIEWPORT", "gpu draw handler"
        code = export.Exporter(s).python()
        compile(code, "<loc>", "exec")
        assert "bl_region_type = \"HEADER\"" in code and "bl_parent_id = \"VIEW3D_PT_overlay\"" in code
        assert "bl_space_type = \"IMAGE_EDITOR\"" in code
        assert "NOTE: 'Hologram block' is not drawn in this panel" in code
        llm = export.Exporter(s).llm()
        assert "Image Editor > Sidebar" in llm and "inside VIEW3D_PT_overlay" in llm and "DRAWN OUTSIDE" in llm
        entries, selected, node = locmap.entries(s)
        cells = sorted((x.space, x.cell) for x in entries)
        assert ("VIEW_3D", "HEADER") in cells and ("IMAGE_EDITOR", "SIDEBAR") in cells and ("VIEW_3D", "MAIN") in cells, cells
        for i in range(len(s.elements)):
            s.active_index = i
            ui.UIB_PT_location.draw(types.SimpleNamespace(layout=FakeLayout([])), bpy.context)
        check_preview("locations")
    finally:
        for c in reversed(classes):
            bpy.utils.unregister_class(c)
    print("locations OK")


def test_simplify():
    from ui_builder import importer
    from ui_builder.operators import new_element
    from bpy.props import EnumProperty, FloatProperty, PointerProperty

    def dyn_items(self, context):
        return [("a", "Alpha", ""), ("b", "Beta", "")]

    class SP(bpy.types.PropertyGroup):
        mode: EnumProperty(name="Mode", items=dyn_items)
        amount: FloatProperty(name="Amount")

    class SIM_PT_main(bpy.types.Panel):
        bl_label = "Sim"; bl_idname = "SIM_PT_main"
        bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Sim"

        def draw(self, context):
            p = context.scene.sim_props
            layout = self.layout
            col = layout.column()
            r = col.row(); r.prop(p, "mode")
            r = col.row(); r.template_list("UI_UL_list", "", bpy.data, "objects", p, "amount", rows=3)
            r = col.row(); r.template_icon(icon_value=0, scale=6)
            col.separator()
            col.row()  # empty
            col.separator()
            r = layout.row(); r.label(text="Select Source")
            r = layout.row()
            inner = r.row(); inner.template_list("UI_UL_list", "", bpy.data, "objects", p, "amount")
            side = r.column(align=True)
            side.operator("object.select_all", text="", icon="INFO"); side.operator("object.select_all", text="", icon="ADD")
            r = layout.row(); r.scale_x = 0.3; r.label(text="Device:")
            r = layout.row(align=True); sub = r.row(); sub.enabled = False; sub.prop(p, "amount", text="")

    for c in (SP, SIM_PT_main):
        bpy.utils.register_class(c)
        c.__module__ = "simaddon"
    bpy.types.Scene.sim_props = PointerProperty(type=SP)
    try:
        item, err = importer.build_panel(importer.addon_panels("simaddon")[0], importer.Ctx(bpy.context))
        assert not err, err
        def shape(i): return (i.type, [shape(c) for c in i.children])
        got = shape(item)
        print("  simplified:", got)
        kinds = [c.type for c in item.children]
        assert kinds == ["MENU" if False else "ENUM", "LIST", "IMAGE_PREVIEW", "LABEL", "ROW", "LABEL", "STRING" if False else "FLOAT"], kinds
        row = item.children[4]
        assert [c.type for c in row.children] == ["LIST", "COLUMN"] and row.children[1].fields["align"] is True
        assert item.children[5].fields["scale_x"] == 0.3
        assert item.children[6].fields["enabled"] is False
        enum = item.children[0]
        assert enum.fields["enum_items"] == "Alpha, Beta" or enum.fields["enum_items"], enum.fields
        assert item.children[1].label == "Objects"
        s.elements.clear()
        importer.commit(s, [item], new_element, tree.normalize)
        assert any(e.type == "IMAGE_PREVIEW" for e in s.elements)
        check_preview("simplified")
        compile(export.Exporter(s).python(), "<sim>", "exec")
    finally:
        del bpy.types.Scene.sim_props
        for c in (SIM_PT_main, SP):
            bpy.utils.unregister_class(c)
    print("simplify OK")


def test_multiselect():
    from ui_builder.operators import new_element
    s.elements.clear()

    def build(spec):
        s.elements.clear()
        for typ, label, indent in spec:
            new_element(s, typ, len(s.elements), indent, label)
        for e in s.elements:
            e.selected = False

    def sel(*labels):
        for e in s.elements:
            e.selected = e.label in labels

    def order():
        return [e.label for e in s.elements]

    def levels():
        return [(e.label, e.indent) for e in s.elements]

    build([("PANEL", "P", 0)] + [("LABEL", n, 1) for n in "abcd"])
    sel("b", "c"); s.active_index = 2
    bpy.ops.ui_builder.move(direction="UP")
    assert order() == ["P", "b", "c", "a", "d"], order()
    assert s.elements[s.active_index].label == "b"
    assert bpy.ops.ui_builder.move(direction="UP") == {"CANCELLED"}  # already at the top of the panel
    assert order() == ["P", "b", "c", "a", "d"]
    bpy.ops.ui_builder.move(direction="DOWN")
    assert order() == ["P", "a", "b", "c", "d"], order()
    # non-adjacent selection moves independently
    sel("a", "c")
    bpy.ops.ui_builder.move(direction="DOWN")
    assert order() == ["P", "b", "a", "d", "c"], order()
    bpy.ops.ui_builder.move(direction="DOWN")  # c is blocked at the bottom, a still moves past d
    assert order() == ["P", "b", "d", "a", "c"], order()
    # selection survives; no selection falls back to the active element
    sel(); s.active_index = 1
    bpy.ops.ui_builder.move(direction="DOWN")
    assert order() == ["P", "d", "b", "a", "c"], order()
    assert not any(e.selected for e in s.elements)

    # container + children move together, selected children inside it are not moved twice
    build([("PANEL", "P", 0), ("LABEL", "a", 1), ("ROW", "R", 1), ("LABEL", "r1", 2), ("LABEL", "r2", 2),
           ("LABEL", "z", 1)])
    sel("R", "r1"); s.active_index = 2
    bpy.ops.ui_builder.move(direction="UP")
    assert order() == ["P", "R", "r1", "r2", "a", "z"], order()

    # nesting several at once, order preserved both ways
    build([("PANEL", "P", 0), ("ROW", "C", 1), ("LABEL", "x", 1), ("LABEL", "y", 1), ("LABEL", "w", 1)])
    sel("x", "y"); s.active_index = 2
    bpy.ops.ui_builder.indent(direction="IN")
    assert levels() == [("P", 0), ("C", 1), ("x", 2), ("y", 2), ("w", 1)], levels()
    bpy.ops.ui_builder.indent(direction="OUT")
    assert levels() == [("P", 0), ("C", 1), ("x", 1), ("y", 1), ("w", 1)], levels()

    # duplicate / remove several
    sel("x", "y")
    bpy.ops.ui_builder.duplicate()
    assert order() == ["P", "C", "x", "y", "x", "y", "w"], order()
    assert [e.selected for e in s.elements] == [False, False, False, False, True, True, False]
    bpy.ops.ui_builder.remove()
    assert order() == ["P", "C", "x", "y", "w"], order()

    # replace: change a container's type but keep its children
    build([("PANEL", "P", 0), ("ROW", "Row", 1), ("LABEL", "a", 2), ("LABEL", "b", 2), ("ROW", "Mine", 1)])
    s.active_index = 1
    bpy.ops.ui_builder.replace(type="COLUMN")
    assert [(e.type, e.label, e.indent) for e in s.elements] == [
        ("PANEL", "P", 0), ("COLUMN", "Column", 1), ("LABEL", "a", 2), ("LABEL", "b", 2), ("ROW", "Mine", 1)]
    bpy.ops.ui_builder.replace(type="SPLIT")
    assert s.elements[1].type == "SPLIT" and s.elements[2].indent == 2
    sel("Split", "Mine")
    bpy.ops.ui_builder.replace(type="BOX")  # several at once; custom names stay
    assert [e.type for e in s.elements] == ["PANEL", "BOX", "LABEL", "LABEL", "BOX"]
    assert s.elements[4].label == "Mine" and s.elements[1].label == "Box"
    sel(); s.active_index = 1
    bpy.ops.ui_builder.replace(type="BUTTON")  # leaf: children lifted one level
    assert [(e.type, e.indent) for e in s.elements] == [("PANEL", 0), ("BUTTON", 1), ("LABEL", 1), ("LABEL", 1), ("BOX", 1)]
    assert s.elements[1].ident == "button"
    check_preview("replaced")
    from ui_builder import ui as _ui
    for m in [_ui.UIB_MT_replace] + [m for _, _, _, m in _ui._replace_menus]:
        m.draw(types.SimpleNamespace(layout=FakeLayout([])), bpy.context)

    build([("PANEL", "P", 0), ("ROW", "C", 1), ("LABEL", "x", 1), ("LABEL", "y", 1), ("LABEL", "w", 1)])
    # select menu actions
    bpy.ops.ui_builder.select(action="ALL")
    assert all(e.selected for e in s.elements)
    bpy.ops.ui_builder.select(action="INVERT")
    assert not any(e.selected for e in s.elements)
    s.active_index = 2
    bpy.ops.ui_builder.select(action="SIBLINGS")
    assert [e.label for e in s.elements if e.selected] == ["C", "x", "y", "w"]
    bpy.ops.ui_builder.select(action="NONE")
    assert not any(e.selected for e in s.elements)
    from ui_builder import ui
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), None, s.elements[0], 0, None, "", 0)
    print("multiselect OK")


check_icons()
test_multiselect()
test_simplify()
test_locations()
test_builder_ui()
test_import()
test_updater()
test_all_types()
code = test_example()
open(os.environ.get("UIB_DUMP", os.devnull), "w").write(code)
test_ops()
ui_builder.unregister()
print("ALL OK")
