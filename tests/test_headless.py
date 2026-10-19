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
    assert updater.local_version() == (1, 0, 0), updater.local_version()
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
    assert updater.local_version() == (1, 0, 0), updater.local_version()
    shutil.rmtree(fake_addon)
    print("updater OK")


check_icons()
test_builder_ui()
test_updater()
test_all_types()
code = test_example()
open(os.environ.get("UIB_DUMP", os.devnull), "w").write(code)
test_ops()
ui_builder.unregister()
print("ALL OK")
