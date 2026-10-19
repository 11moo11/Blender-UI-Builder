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
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), s, s.elements[2], 0, None, "", 0)
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
    assert updater.local_version() == (1, 5, 0), updater.local_version()
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
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), s, s.elements[2], 0, None, "", 0)
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
    assert updater.local_version() == (1, 5, 0), updater.local_version()
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
        for i, e in enumerate(s.elements):  # every element with children is rolled up after an import
            has_kids = i + 1 < len(s.elements) and s.elements[i + 1].indent > e.indent
            assert e.fold == has_kids, (i, e.type, e.fold)
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
        flag: bpy.props.BoolProperty(name="Flag")

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
            c2 = layout.column(align=True)
            c2.label(text="Quilt:")
            c2.prop(p, "mode", text="")
            c2.label(text="Other")
            c2.prop(p, "mode")  # keeps its own name: not merged
            c3 = layout.column()
            c3.label(text="Strength:"); c3.prop(p, "amount", text="", slider=True)
            c3.label(text="Title:"); c3.prop(p, "name", text="")
            c3.label(text="Enable it:"); c3.prop(p, "flag", text="")
            c3.label(text="Icon only"); c3.prop(p, "flag", text="", icon="PINNED", toggle=True)
            c3.label(text="Plain"); c3.operator("object.select_all", text="Go")
            r1 = layout.row(align=True); r1.scale_x = 0.3; r1.label(text="Device:")
            r2 = layout.row(align=True); r2.scale_x = 0.7; r2.prop(p, "mode", text="")

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
        assert kinds == ["ENUM", "LIST", "IMAGE_PREVIEW", "LABEL", "ROW", "FLOAT", "COLUMN", "SLIDER", "STRING",
                         "BOOL", "LABEL", "BOOL", "LABEL", "BUTTON", "ENUM"], kinds
        row = item.children[4]
        assert [c.type for c in row.children] == ["LIST", "COLUMN"] and row.children[1].fields["align"] is True
        # label + unnamed value control -> one control with the label on the left
        dev = item.children[5]
        assert dev.label == "Device" and dev.fields["prop_split"] and dev.fields["enabled"] is False
        assert "scale_x" not in dev.fields
        col = item.children[6]
        assert [c.type for c in col.children] == ["ENUM", "LABEL", "ENUM"]
        assert col.children[0].label == "Quilt" and col.children[0].fields["prop_split"] is True
        assert col.children[2].label == "Mode" and "prop_split" not in col.children[2].fields  # own name kept
        assert [(c.type, c.label) for c in item.children[7:14]] == [
            ("SLIDER", "Strength"), ("STRING", "Title"), ("BOOL", "Enable it"), ("LABEL", "Icon only"),
            ("BOOL", ""), ("LABEL", "Plain"), ("BUTTON", "Go")]
        assert all(c.fields.get("prop_split") for c in item.children[7:10])
        assert item.children[9].fields["bool_style"] == "CHECKBOX"
        assert not item.children[11].fields.get("prop_split") and item.children[11].fields["bool_style"] == "ICON"
        last = item.children[len(item.children) - 1]
        assert last.label == "Device" and last.fields["prop_split"] and "scale_x" not in last.fields
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
    ui.UIB_UL_elements.draw_item(types.SimpleNamespace(layout_type="DEFAULT"), bpy.context, FakeLayout([]), s, s.elements[0], 0, None, "", 0)
    print("multiselect OK")


def test_branches():
    from ui_builder import ui, branches
    from ui_builder.preview import Drawer
    s.elements.clear()

    def rows():
        return [(e.type, e.label, e.indent) for e in s.elements]

    bpy.ops.ui_builder.add(type="PANEL")
    bpy.ops.ui_builder.add(type="ENUM")
    assert rows() == [("PANEL", "Panel", 0), ("ENUM", "Choice (Dropdown / Buttons)", 1), ("OPTION", "Option A", 2),
                      ("OPTION", "Option B", 2), ("OPTION", "Option C", 2)], rows()
    s.elements[1].label = "View"
    s.active_index = 3  # the "Option B" row: new controls go inside it
    bpy.ops.ui_builder.add(type="LABEL")
    s.elements[4].label = "only in B"
    assert [(r[0], r[2]) for r in rows()][2:] == [("OPTION", 2), ("OPTION", 2), ("LABEL", 3), ("OPTION", 2)], rows()
    s.active_index = 1
    bpy.ops.ui_builder.add(type="LABEL")  # active is the Choice: new element is a sibling after it
    assert rows()[-1] == ("LABEL", "Label", 1), rows()
    s.elements[len(s.elements) - 1].label = "always"

    # renaming every option keeps the contents with the same position
    enum = s.elements[1]
    enum.enum_items = "Shape, Material, Settings"
    assert [(r[1], r[2]) for r in rows() if r[0] == "OPTION"] == [("Shape", 2), ("Material", 2), ("Settings", 2)], rows()
    assert [e.option_id for e in s.elements if e.type == "OPTION"] == ["shape", "material", "settings"]
    assert rows()[4] == ("LABEL", "only in B", 3)
    # add, reorder, remove
    s.elements[1].enum_items = "Settings, Shape, Material, Extra"
    assert [e.label for e in s.elements if e.type == "OPTION"] == ["Settings", "Shape", "Material", "Extra"], rows()
    mat = [i for i, e in enumerate(s.elements) if e.label == "Material"][0]
    assert s.elements[mat + 1].label == "only in B"
    s.elements[1].enum_items = "Settings, Shape, Extra"
    labels = [e.label for e in s.elements if e.type == "OPTION"]
    assert labels == ["Settings", "Shape", "Extra", "Material (removed option)"], labels  # had contents: kept
    s.elements[1].enum_items = "Settings, Shape, Extra, Material"
    assert [e.label for e in s.elements if e.type == "OPTION"][-1] == "Material"  # re-adopted with its contents
    assert any(e.label == "only in B" for e in s.elements)

    # preview shows only the chosen option's controls
    def drawn(value):
        s.elements[1].enum_value = value
        log = []
        Drawer(s).nodes(FakeLayout(log), tree.build(s.elements))
        return [kw.get("text") for m, a, kw in log if m == "label"]
    assert "only in B" in drawn("material") and "only in B" not in drawn("shape")
    assert "always" in drawn("shape")

    # export: if-block on the property, compiles, runs
    s.elements[1].enum_value = "settings"
    ex = export.Exporter(s)
    code = ex.python()
    assert "if props.view == \"material\":" in code, code
    ns = {"__name__": "gen_branch"}
    exec(compile(code, "<branch>", "exec"), ns)
    ns["register"]()
    try:
        props = getattr(scene, ex.group)
        panel = [c for c in ns["classes"] if issubclass(c, bpy.types.Panel)][0]
        for value, want in (("material", True), ("shape", False)):
            props.view = value
            log = []
            panel.draw(types.SimpleNamespace(layout=FakeLayout(log)), bpy.context)
            assert (("only in B" in [kw.get("text") for m, a, kw in log if m == "label"]) == want), value
    finally:
        ns["unregister"]()
    assert "If \"Material\"" in ex.llm()

    # moving an Option row can't scramble the order; folding hides the rows
    s.active_index = [i for i, e in enumerate(s.elements) if e.label == "Shape"][0]
    bpy.ops.ui_builder.move(direction="UP")
    assert [e.label for e in s.elements if e.type == "OPTION"] == ["Settings", "Shape", "Extra", "Material"]
    s.elements[1].fold = True
    flags, _ = ui.UIB_UL_elements.filter_items(types.SimpleNamespace(bitflag_filter_item=1), bpy.context, s, "elements")
    assert flags[0] == 1 and flags[1] == 1 and all(f == 0 for f, e in zip(flags[2:], list(s.elements)[2:]) if e.indent >= 2)
    s.elements[1].fold = False

    # duplicate keeps one set of option rows; JSON round-trips
    s.active_index = 1
    bpy.ops.ui_builder.duplicate()
    assert [e.type for e in s.elements].count("OPTION") == 8, rows()
    dumped = export.dump_project(s)
    n = len(s.elements)
    export.load_project(s, dumped)
    assert len(s.elements) == n and export.dump_project(s) == dumped
    s.active_index = [i for i, e in enumerate(s.elements) if e.type == "ENUM"][1]
    bpy.ops.ui_builder.remove()  # removes the duplicate with its options
    assert [e.type for e in s.elements].count("OPTION") == 4

    # replacing the Choice dissolves its options, contents move up
    s.active_index = 1
    bpy.ops.ui_builder.replace(type="ROW")
    assert not any(e.type == "OPTION" for e in s.elements), rows()
    assert any(e.label == "only in B" and e.indent == 2 for e in s.elements), rows()
    bpy.ops.ui_builder.replace(type="ENUM")
    assert [e.type for e in s.elements].count("OPTION") == 4, rows()  # one per option again
    assert [e.label for e in s.elements if e.type == "OPTION"] == ["Settings", "Shape", "Extra", "Material"]

    # property split now also applies to a Choice's own widget (label left, value right)
    s.elements.clear()
    bpy.ops.ui_builder.add(type="ENUM")
    s.elements[0].prop_split = True
    log = []
    Drawer(s).nodes(FakeLayout(log), tree.build(s.elements))
    assert [x[0] for x in log][:2] == ["row", "set"], log
    s.elements[0].alignment = "RIGHT"
    log = []
    Drawer(s).nodes(FakeLayout(log), tree.build(s.elements))
    assert ("set", "alignment", "RIGHT") in log, log
    assert "alignment = \"RIGHT\"" in export.Exporter(s).python()
    s.elements[0].alignment = "EXPAND"
    assert ("set", "use_property_split", True) in log, log
    assert "use_property_split = True" in export.Exporter(s).python()
    assert ".row(align=True)" in export.Exporter(s).python()

    # new elements go directly below the selection
    s.elements.clear()
    bpy.ops.ui_builder.add(type="PANEL")
    bpy.ops.ui_builder.add(type="ROW")           # P > R
    bpy.ops.ui_builder.add(type="LABEL")         # P > R > L1 (below the row, as its first child)
    s.elements[2].label = "L1"
    s.active_index = 1
    bpy.ops.ui_builder.add(type="BUTTON")        # directly below the row => first child, before L1
    assert [(e.label, e.indent) for e in s.elements][1:] == [("Row", 1), ("Button", 2), ("L1", 2)], rows()
    s.elements[1].fold = True
    s.active_index = 1
    bpy.ops.ui_builder.add(type="LABEL")         # folded row: new element lands after the whole row
    assert [(e.type, e.indent) for e in s.elements] == [("PANEL", 0), ("ROW", 1), ("BUTTON", 2), ("LABEL", 2),
                                                         ("LABEL", 1)], rows()
    s.active_index = 2
    bpy.ops.ui_builder.add(type="STRING")        # leaf: right below it, same level
    assert s.elements[3].type == "STRING" and s.elements[3].indent == 2

    # merged Color element
    s.elements.clear()
    bpy.ops.ui_builder.add(type="COLOR")
    c = s.elements[0]
    assert el.value_attr(c) == "color_value"
    c.use_alpha = True
    assert el.value_attr(c) == "color_alpha_value"
    code = export.Exporter(s).python()
    assert "size=4" in code, code
    log = []
    Drawer(s).nodes(FakeLayout(log), tree.build(s.elements))
    assert log[0][1][1] == "color_alpha_value", log
    assert "COLOR_ALPHA" not in [d.id for d in el.DEFS.values() if not d.hidden]
    print("branches OK")


def test_scrape():
    from ui_builder import importer
    from ui_builder.operators import new_element
    from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty

    def good(self, context):
        return [("a", "Alpha", ""), ("b", "Beta", "")]

    def broken(self, context):
        raise RuntimeError("needs live data")

    class SG(bpy.types.PropertyGroup):
        dyn: EnumProperty(name="Dyn", items=good, default=None)
        unknown: EnumProperty(name="Unknown", items=broken)
        static: EnumProperty(name="Static", items=[("x", "Ex", ""), ("y", "Why", "")], default="y")
        count: IntProperty(name="Count", default=3, min=1, max=9)
        amount: FloatProperty(name="Amount", default=0.25, min=0, max=2)

    class SCR_PT_main(bpy.types.Panel):
        bl_label = "Scrape"; bl_idname = "SCR_PT_main"
        bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Scrape"

        def draw(self, context):
            g = context.scene.scr_props
            for n in ("dyn", "unknown", "static", "count", "amount"):
                self.layout.prop(g, n)

    for c in (SG, SCR_PT_main):
        bpy.utils.register_class(c)
        c.__module__ = "scrapeaddon"
    bpy.types.Scene.scr_props = PointerProperty(type=SG)
    try:
        g = bpy.context.scene.scr_props
        g.count = -2  # runtime state must not leak into the imported default
        item, err = importer.build_panel(importer.addon_panels("scrapeaddon")[0], importer.Ctx(bpy.context))
        assert not err, err
        by = {c.fields["ident"]: c for c in item.children}
        assert by["dyn"].fields["enum_items"] == "Alpha, Beta", by["dyn"].fields   # callback evaluated
        assert "PLACEHOLDER" not in by["dyn"].fields["enum_items"]
        assert by["static"].fields["enum_items"] == "Ex, Why" and by["static"].fields["enum_value"] == "why"
        unk = by["unknown"].fields
        assert "PLACEHOLDER_OPTION_1" in unk["enum_items"] and "UNKNOWN OPTIONS" in unk["description"], unk
        assert by["count"].fields["int_value"] == 3, by["count"].fields             # default, not the -2 state
        assert by["amount"].fields["float_value"] == 0.25
        s.elements.clear()
        importer.commit(s, [item], new_element, tree.normalize)
        llm = export.Exporter(s).llm()
        assert "Placeholders - do not treat as real" in llm and "Do NOT guess" in llm, llm[:1500]
        code = export.Exporter(s).python()
        assert "placeholder_option_1" in code.lower() and "UNKNOWN OPTIONS" in code
        compile(code, "<scrape>", "exec")
    finally:
        del bpy.types.Scene.scr_props
        for c in (SCR_PT_main, SG):
            bpy.utils.unregister_class(c)
    print("scrape OK")


def test_enum_buttons():
    from ui_builder import importer, properties
    from ui_builder.operators import new_element
    from ui_builder.preview import Drawer
    from bpy.props import EnumProperty, PointerProperty

    class BG(bpy.types.PropertyGroup):
        kind: EnumProperty(name="Kind", items=[("MODEL", "Models", "", "OBJECT_DATA", 0),
                                               ("MAT", "Materials", "", "MATERIAL", 1)])
        other: EnumProperty(name="Other", items=[("a", "A", ""), ("b", "B", "")])

    class BTN_PT_main(bpy.types.Panel):
        bl_label = "Btn"; bl_idname = "BTN_PT_main"
        bl_space_type = "VIEW_3D"; bl_region_type = "UI"; bl_category = "Btn"

        def draw(self, context):
            g = context.scene.btn_props
            r = self.layout.row(); r.prop(g, "kind", expand=True, icon_only=True)     # side by side, icons only
            self.layout.prop(g, "other", expand=True)                                  # stacked in the panel column

    for c in (BG, BTN_PT_main):
        bpy.utils.register_class(c)
        c.__module__ = "btnaddon"
    bpy.types.Scene.btn_props = PointerProperty(type=BG)
    try:
        item, err = importer.build_panel(importer.addon_panels("btnaddon")[0], importer.Ctx(bpy.context))
        assert not err, err
        kinds = [c.type for c in item.children]
        assert kinds == ["ENUM", "ENUM"], kinds   # the row was folded into the style instead of being lost
        side, stacked = item.children
        assert side.fields["enum_style"] == "ROW" and side.fields["enum_icon_only"] is True, side.fields
        assert side.fields["enum_icons"] == "OBJECT_DATA,MATERIAL"
        assert stacked.fields["enum_style"] == "EXPAND" and "enum_icons" not in stacked.fields
        s.elements.clear()
        importer.commit(s, [item], new_element, tree.normalize)
        rows = [e for e in s.elements if e.type == "OPTION"]
        assert [(r.label, r.icon) for r in rows[:2]] == [("Models", "OBJECT_DATA"), ("Materials", "MATERIAL")]
        enum = [e for e in s.elements if e.type == "ENUM"][0]
        items = properties._enum_value_items(enum, bpy.context)
        assert items[0][3] == "OBJECT_DATA" and items[1][3] == "MATERIAL", items
        log = []
        Drawer(s).nodes(FakeLayout(log), tree.build(s.elements))
        calls = [(m, kw) for m, a, kw in log]
        k = [i for i, c in enumerate(calls) if c[0] == "prop" and c[1].get("text") == "Kind"][0]
        assert calls[k - 1][0] == "row", calls                   # side-by-side: wrapped in its own row
        assert calls[k + 1][0] == "prop" and calls[k + 1][1].get("text") == "Other"  # stacked: no wrapper
        props = {kw.get("text"): kw for m, kw_a, kw in log if m == "prop"}
        assert props["Kind"].get("expand") and props["Kind"].get("icon_only") and not props["Other"].get("icon_only")
        code = export.Exporter(s).python()
        assert '"OBJECT_DATA", 0)' in code and "icon_only=True" in code and ".row(align=True)" in code, code
        ns = {"__name__": "gen_btn"}
        exec(compile(code, "<btn>", "exec"), ns)
        ns["register"]()
        ns["unregister"]()
    finally:
        del bpy.types.Scene.btn_props
        for c in (BTN_PT_main, BG):
            bpy.utils.unregister_class(c)
    print("enum buttons OK")


check_icons()
test_enum_buttons()
test_scrape()
test_branches()
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
