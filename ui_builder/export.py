"""Code generation: Python addon, LLM prompt and JSON project."""

import json
import re

import bpy

from . import branches
from . import elements as el
from . import tree

FORMAT_VERSION = 1
_NO_LABEL = {"OPTION", "ROW", "COLUMN", "BOX", "SPLIT", "GRID", "SEPARATOR", "SPACER", "TEXT_LINES"}


def _lit(v):
    if isinstance(v, float):
        return repr(round(v, 4))
    if isinstance(v, (tuple, list)):
        return "(%s)" % ", ".join(_lit(x) for x in v) + ("" if len(v) != 1 else "")
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return repr(v)


class Raw(str):
    """Literal source code (not quoted)."""


def _arg(v):
    return str(v) if isinstance(v, Raw) else _lit(v)


class Exporter:
    def __init__(self, settings):
        self.s = settings
        self.prefix = el.slugify(settings.prefix, "my_addon")
        self.PFX = self.prefix.upper()
        self.addon_name = settings.addon_name or "My Addon"
        self.group = "%s_props" % self.prefix  # Scene attribute holding the property group
        self.group_cls = "%s_Properties" % self.PFX
        self.item_cls = "%s_ListItem" % self.PFX
        self.roots = tree.build(settings.elements)
        self.nodes = list(tree.walk(self.roots))
        self._assign_names()
        self.place = el.project_place(settings)
        self.region = self.place.region
        self.has_list = any(n.elem.type == "LIST" for n in self.nodes)
        self.prop_lines = []  # property group annotations
        self.operators = []  # (idname, class name, label, description)
        self.menus = []  # (class name, label, [(item operator idname, item label)])
        self.uilists = []
        self.popovers = []
        self.panels = []
        self.header_notes = []
        self._var_count = 0

    # -- naming ----------------------------------------------------------------
    def _assign_names(self):
        used = set()
        for n in self.nodes:
            base = el.slugify(n.elem.ident or n.elem.label, el.slugify(n.elem.type))
            name, k = base, 2
            while name in used:
                name = "%s_%d" % (base, k)
                k += 1
            used.add(name)
            n.name = name

    def cls(self, kind, n):
        return "%s_%s_%s" % (self.PFX, kind, n.name)

    def var(self, base):
        self._var_count += 1
        return "%s%d" % (base, self._var_count)

    # -- property definitions ------------------------------------------------------
    def _decl(self, attr, ctor, kw):
        lines = ["    %s: %s(" % (attr, ctor)]
        for k, v in kw.items():
            lines.append("        %s=%s," % (k, _arg(v)))
        lines.append("    )")
        return lines

    def _base_kw(self, n, name=None):
        kw = {"name": name or n.elem.label or n.name}
        if n.elem.description:
            kw["description"] = n.elem.description
        return kw

    def property_defs(self, n):
        e, t, a = n.elem, n.elem.type, n.name
        kw = self._base_kw(n)
        val = getattr(e, el.value_attr(e)) if t in el.VALUE_ATTR else None

        def rng(kw, lo=None, hi=None):
            if e.use_range:
                kw["min"], kw["max"] = (e.range_min, e.range_max)
                if t == "INT":
                    kw["min"], kw["max"] = int(e.range_min), int(e.range_max)
            else:
                if lo is not None:
                    kw["min"] = lo
                if hi is not None:
                    kw["max"] = hi

        if t == "BOOL":
            kw["default"] = bool(val)
            return self._decl(a, "BoolProperty", kw), "BoolProperty"
        if t == "INT":
            kw["default"] = int(val)
            rng(kw)
            return self._decl(a, "IntProperty", kw), "IntProperty"
        if t in ("FLOAT", "SLIDER", "FACTOR", "PERCENT", "ANGLE", "DISTANCE"):
            kw["default"] = float(val)
            if t in ("SLIDER", "FACTOR"):
                rng(kw, 0.0, 1.0)
            elif t == "PERCENT":
                rng(kw, 0.0, 100.0)
            else:
                rng(kw)
            sub = {"FACTOR": "FACTOR", "PERCENT": "PERCENTAGE", "ANGLE": "ANGLE", "DISTANCE": "DISTANCE"}.get(t)
            if sub:
                kw["subtype"] = sub
            if t == "ANGLE":
                kw["unit"] = "ROTATION"
            if t == "DISTANCE":
                kw["unit"] = "LENGTH"
            return self._decl(a, "FloatProperty", kw), "FloatProperty"
        if t in ("STRING", "SEARCH", "FILEPATH", "DIRPATH"):
            kw["default"] = val
            if t == "FILEPATH":
                kw["subtype"] = "FILE_PATH"
            elif t == "DIRPATH":
                kw["subtype"] = "DIR_PATH"
            return self._decl(a, "StringProperty", kw), "StringProperty"
        if t == "ENUM":
            items = el.parse_enum_items(e.enum_items)
            kw["items"] = Raw("[%s]" % ", ".join("(%s, %s, \"\")" % (_lit(i[0]), _lit(i[1])) for i in items))
            kw["default"] = val
            return self._decl(a, "EnumProperty", kw), "EnumProperty"
        if t in ("COLOR", "COLOR_PICKER", "COLOR_ALPHA", "VEC2", "VEC3", "EULER"):
            size = {"COLOR": 4 if e.use_alpha else 3, "COLOR_PICKER": 3, "COLOR_ALPHA": 4, "VEC2": 2,
                    "VEC3": 3, "EULER": 3}[t]
            kw["size"] = size
            kw["default"] = tuple(round(x, 4) for x in val)
            if t.startswith("COLOR"):
                kw["subtype"] = "COLOR"
                kw["min"], kw["max"] = 0.0, 1.0
            elif t == "VEC3":
                kw["subtype"] = "XYZ"
            elif t == "EULER":
                kw["subtype"] = "EULER"
            return self._decl(a, "FloatVectorProperty", kw), "FloatVectorProperty"
        if t in ("POINTER", "TEMPLATE_ID"):
            kw["type"] = Raw("bpy.types.%s" % el.ID_TYPES[e.id_type][0])
            return self._decl(a, "PointerProperty", kw), "PointerProperty"
        if t == "PROGRESS":
            kw["default"] = round(float(val), 4)
            kw["min"], kw["max"] = 0.0, 1.0
            kw["subtype"] = "FACTOR"
            return self._decl(a, "FloatProperty", kw), "FloatProperty"
        if t == "LIST":
            lines = self._decl(a + "_items", "CollectionProperty", {"type": Raw(self.item_cls)})
            lines += self._decl(a + "_index", "IntProperty", {"name": (e.label or a) + " Index"})
            return lines, "CollectionProperty"
        return None, None

    # -- layout code -----------------------------------------------------------------
    def _resolve(self, n, spec):
        e = n.elem
        out = []
        for a in spec.args:
            if isinstance(a, el.Ref):
                if a.kind == "value":
                    out += [Raw("props"), n.name]
                elif a.kind == "items":
                    out += [Raw("props"), n.name + "_items"]
                else:
                    out += [Raw("props"), n.name + "_index"]
            elif isinstance(a, el.Sym):
                out.append(self._sym(n, a.name))
            else:
                out.append(a)
        kwargs = {k: (self._sym(n, v.name) if isinstance(v, el.Sym) else v) for k, v in spec.kwargs.items()}
        return out, kwargs

    def _sym(self, n, name):
        if name == "bpy.data":
            return Raw("bpy.data")
        if name == "operator":
            return "%s.%s" % (self.prefix, n.name)
        if name == "uilist":
            return self.cls("UL", n)
        if name == "menu":
            return self.cls("MT", n)
        if name == "popover":
            return self.cls("PT", n)
        if name == "preview_icon":
            return Raw("0")
        if name == "value":
            return Raw("props.%s" % n.name)
        raise KeyError(name)

    def call_line(self, target, n, spec):
        args, kwargs = self._resolve(n, spec)
        parts = [_arg(a) for a in args] + ["%s=%s" % (k, _arg(v)) for k, v in kwargs.items()]
        line = "%s.%s(%s)" % (target, spec.method, ", ".join(parts))
        if spec.method == "template_icon":
            line += "  # TODO: icon_value = the icon id of your preview image"
        return line

    def gen_children(self, nodes, layout, ind, out):
        for n in nodes:
            if n.is_panel:
                continue  # emitted as its own bpy.types.Panel
            if n.elem.type != "PANEL" and n.elem.location != "PANEL":
                note = ("%s - %s" % (el.LOCATIONS[n.elem.location][0], n.elem.location_note)
                        if n.elem.location_note else el.LOCATIONS[n.elem.location][0])
                out.append("%s# NOTE: %r is not drawn in this panel; it lives in: %s"
                           % ("    " * ind, n.elem.label or n.name, note))
                continue
            self.gen_node(n, layout, ind, out)

    def gen_branches(self, n, layout, ind, out):
        """`if props.choice == 'a': ...` blocks, one per option that has contents."""
        first = True
        for child in n.children:
            if child.elem.type != "OPTION":
                self.gen_children([child], layout, ind, out)
                continue
            body = []
            self.gen_children(child.children, layout, ind + 1, body)
            if not body:
                continue
            out.append("%s%s props.%s == %s:  # %s" % (
                "    " * ind, "if" if first else "elif", n.name, _lit(child.elem.option_id),
                child.elem.label.replace("\n", " ")))
            out += body
            first = False

    def gen_node(self, n, layout, ind, out):
        e = n.elem
        pad = "    " * ind
        d = el.DEFS[e.type]
        if e.type == "POPOVER":
            attrs = el.layout_attrs(e, False)
            target = layout
            if attrs:
                target = self.var("sub")
                out.append("%s%s = %s.%s(align=True)" % (pad, target, layout, el.wrapper_method(e)))
                out += ["%s%s.%s = %s" % (pad, target, k, _arg(v)) for k, v in attrs]
            for spec in el.leaf_specs(e, export=True):
                out.append(pad + self.call_line(target, n, spec))
            return
        if not d.container or e.type == "ENUM":
            target = layout
            attrs = el.layout_attrs(e, False)
            if attrs:
                target = self.var("sub")
                out.append("%s%s = %s.%s(align=True)" % (pad, target, layout, el.wrapper_method(e)))
                out += ["%s%s.%s = %s" % (pad, target, k, _arg(v)) for k, v in attrs]
            for spec in el.leaf_specs(e, export=True):
                out.append(pad + self.call_line(target, n, spec))
            if e.type == "ENUM":
                self.gen_branches(n, layout, ind, out)
            return
        if e.type == "OPTION":  # stray row
            self.gen_children(n.children, layout, ind, out)
            return
        attrs = el.layout_attrs(e, True)
        if n.is_collapsible:
            box, head, body = self.var("box"), self.var("header"), self.var("body")
            flag = "props.%s_expanded" % n.name
            out.append("%s%s = %s.box()" % (pad, box, layout))
            out.append("%s%s = %s.row()" % (pad, head, box))
            out.append("%s%s.prop(props, %s, text=%s, icon='TRIA_DOWN' if %s else 'TRIA_RIGHT', emboss=False)"
                       % (pad, head, _lit(n.name + "_expanded"), _arg(e.label), flag))
            out.append("%sif %s:" % (pad, flag))
            out.append("%s    %s = %s.column()" % (pad, body, box))
            out += ["%s    %s.%s = %s" % (pad, body, k, _arg(v)) for k, v in attrs]
            self.gen_children(n.children, body, ind + 1, out)
            return
        method, kw = el.container_spec(e)
        var = self.var(method.split("_")[0])
        kws = ", ".join("%s=%s" % (k, _arg(v)) for k, v in kw.items())
        out.append("%s%s = %s.%s(%s)" % (pad, var, layout, method, kws))
        out += ["%s%s.%s = %s" % (pad, var, k, _arg(v)) for k, v in attrs]
        self.gen_children(n.children, var, ind, out)

    def draw_body(self, nodes, layout_expr_attrs=()):
        out = ["        layout = self.layout", "        props = context.scene.%s" % self.group]
        for k, v in layout_expr_attrs:
            out.append("        layout.%s = %s" % (k, _arg(v)))
        n0 = len(out)
        self.gen_children(nodes, "layout", 2, out)
        if len(out) == n0:
            out.append("        pass")
        return out

    # -- class generation ----------------------------------------------------------
    def _panel_header(self, bl_idname, label, parent=None, closed=False, instanced=False, place=None):
        place = place or self.place
        lines = ["class %s(bpy.types.Panel):" % bl_idname,
                 "    bl_idname = %s" % _lit(bl_idname),
                 "    bl_label = %s" % _arg(label),
                 "    bl_space_type = %s" % _lit(place.space),
                 "    bl_region_type = %s" % _lit(place.region)]
        if place.context:
            lines.append("    bl_context = %s" % _lit(place.context))
        if place.region == "UI":
            lines.append("    bl_category = %s" % _arg(place.category or self.s.category or self.addon_name))
        if parent:
            lines.append("    bl_parent_id = %s" % _lit(parent))
        elif place.parent:
            lines.append("    bl_parent_id = %s  # built-in panel this one is shown inside" % _lit(place.parent))
        opts = []
        if closed:
            opts.append("'DEFAULT_CLOSED'")
        if instanced:
            opts.append("'INSTANCED'")
        if opts:
            lines.append("    bl_options = {%s}" % ", ".join(opts))
        return lines

    def gen_panel(self, n, parent_id=None, place=None):
        e = n.elem
        cid = self.cls("PT", n)
        place = place or el.panel_place(e, self.s)
        lines = self._panel_header(cid, e.label or n.name, parent_id, e.default_closed, place=place)
        if e.header_checkbox:
            lines += ["", "    def draw_header(self, context):",
                      "        props = context.scene.%s" % self.group,
                      "        self.layout.prop(props, %s, text=\"\")" % _lit(n.name + "_enabled")]
        lines += ["", "    def draw(self, context):"]
        attrs = el.layout_attrs(e, True)
        lines += self.draw_body(n.children, attrs)
        self.panels.append((cid, lines))
        for c in n.children:
            if c.is_panel:
                self.gen_panel(c, cid, place)

    def gen_support(self):
        for n in self.nodes:
            e = n.elem
            if e.type == "BUTTON":
                self.operators.append((n.name, self.cls("OT", n), e.label, e.description))
            elif e.type == "MENU":
                items = []
                for ident, label in el.parse_enum_items(e.enum_items):
                    opname = "%s_%s" % (n.name, ident)
                    self.operators.append((opname, "%s_OT_%s" % (self.PFX, opname), label, ""))
                    items.append((opname, label))
                self.menus.append((self.cls("MT", n), e.label or n.name, items))
            elif e.type == "LIST":
                self.uilists.append(self.cls("UL", n))
            elif e.type == "POPOVER":
                cid = self.cls("PT", n)
                lines = self._panel_header(cid, e.label or n.name, instanced=True)
                lines += ["", "    def draw(self, context):"]
                lines += self.draw_body(n.children, el.layout_attrs(e, True))
                self.popovers.append((cid, lines))

    def all_property_lines(self):
        lines = []
        for n in self.nodes:
            decl, _ = self.property_defs(n)
            if decl:
                lines += decl
            if n.is_collapsible:
                lines += self._decl(n.name + "_expanded", "BoolProperty",
                                    {"name": (n.elem.label or n.name) + " Expanded",
                                     "default": bool(n.elem.expanded)})
            if n.elem.type == "PANEL" and n.is_panel and n.elem.header_checkbox:
                lines += self._decl(n.name + "_enabled", "BoolProperty",
                                    {"name": n.elem.label or n.name, "default": bool(n.elem.bool_value)})
        ctors = set(re.findall(r"\b(\w+Property)\(", "\n".join(lines)))
        if self.has_list:
            ctors.add("StringProperty")  # list item class
        ctors.add("PointerProperty")  # registers the group on the Scene
        return lines, sorted(ctors)

    # -- python addon ---------------------------------------------------------------
    def python(self):
        self.prop_lines = []
        self.operators, self.menus, self.uilists, self.popovers, self.panels = [], [], [], [], []
        self._var_count = 0
        self.gen_support()

        root_panels = [n for n in self.roots if n.is_panel]
        loose = [n for n in self.roots if not n.is_panel]
        if loose or not root_panels:
            lines = self._panel_header("%s_PT_main" % self.PFX, self.addon_name)
            lines += ["", "    def draw(self, context):"]
            lines += self.draw_body(loose)
            self.panels.append(("%s_PT_main" % self.PFX, lines))
        for n in root_panels:
            self.gen_panel(n)

        prop_lines, ctors = self.all_property_lines()
        loc = el.PLACEMENTS[self.s.placement][0]
        mn = tuple(int(x) for x in self.s.blender_min.split("."))
        out = [
            '"""%s - generated by Blender UI Builder.' % self.addon_name,
            "",
            "The UI is complete; operators are stubs. Look for TODO markers to wire up behaviour.",
            '"""',
            "",
            "bl_info = {",
            "    \"name\": %s," % _arg(self.addon_name),
            "    \"author\": %s," % _arg(self.s.author),
            "    \"version\": (1, 0, 0),",
            "    \"blender\": %s," % _lit(mn),
            "    \"location\": %s," % _arg("%s > %s" % (loc, self.s.category) if self.region == "UI" else loc),
            "    \"description\": %s," % _arg("UI created with Blender UI Builder"),
            "    \"category\": \"Interface\",",
            "}",
            "",
            "import bpy",
            "from bpy.props import %s" % ", ".join(ctors),
            "",
            "",
        ]
        if self.has_list:
            out += ["class %s(bpy.types.PropertyGroup):" % self.item_cls,
                    "    name: StringProperty()", "", ""]
        out += ["class %s(bpy.types.PropertyGroup):" % self.group_cls]
        out += prop_lines if prop_lines else ["    pass"]
        out += ["", ""]

        classes = [self.group_cls]
        if self.has_list:
            classes.insert(0, self.item_cls)
        for idname, cname, label, desc in self.operators:
            out += ["class %s(bpy.types.Operator):" % cname,
                    "    bl_idname = %s" % _lit("%s.%s" % (self.prefix, idname)),
                    "    bl_label = %s" % _arg(label or idname)]
            if desc:
                out.append("    bl_description = %s" % _arg(desc))
            out += ["    bl_options = {'REGISTER', 'UNDO'}", "",
                    "    def execute(self, context):",
                    "        props = context.scene.%s" % self.group,
                    "        # TODO: implement %s" % _lit(label or idname),
                    "        self.report({'INFO'}, %s)" % _arg("%s clicked" % (label or idname)),
                    "        return {'FINISHED'}", "", ""]
            classes.append(cname)
        for cname, label, items in self.menus:
            out += ["class %s(bpy.types.Menu):" % cname,
                    "    bl_idname = %s" % _lit(cname),
                    "    bl_label = %s" % _arg(label), "",
                    "    def draw(self, context):",
                    "        layout = self.layout"]
            for opname, ilabel in items:
                out.append("        layout.operator(%s, text=%s)" % (_lit("%s.%s" % (self.prefix, opname)), _arg(ilabel)))
            out += ["", ""]
            classes.append(cname)
        for cname in self.uilists:
            out += ["class %s(bpy.types.UIList):" % cname,
                    "    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):",
                    "        # TODO: draw your item (add properties to %s as needed)" % self.item_cls,
                    "        if self.layout_type in {'DEFAULT', 'COMPACT'}:",
                    "            layout.prop(item, \"name\", text=\"\", emboss=False, icon_value=icon)",
                    "        elif self.layout_type == 'GRID':",
                    "            layout.alignment = 'CENTER'",
                    "            layout.label(text=\"\", icon_value=icon)", "", ""]
            classes.append(cname)
        for cid, lines in self.popovers + self.panels:
            out += lines + ["", ""]
            classes.append(cid)

        out += ["classes = (" ] + ["    %s," % c for c in classes] + [")", "", "",
                "def register():",
                "    for cls in classes:",
                "        bpy.utils.register_class(cls)",
                "    bpy.types.Scene.%s = PointerProperty(type=%s)" % (self.group, self.group_cls),
                "", "",
                "def unregister():",
                "    del bpy.types.Scene.%s" % self.group,
                "    for cls in reversed(classes):",
                "        bpy.utils.unregister_class(cls)", "", "",
                "if __name__ == \"__main__\":",
                "    register()", ""]
        return "\n".join(out)

    # -- LLM prompt -------------------------------------------------------------
    def outline(self):
        lines = []

        def describe(n):
            e = n.elem
            d = el.DEFS[e.type]
            if e.type == "OPTION":
                return "If \"%s\" is chosen (`%s`)%s" % (e.label, e.option_id,
                                                         "" if n.children else " - nothing extra shown")
            kind = "Sub-panel" if e.type == "PANEL" and n.parent else d.label
            if n.is_collapsible:
                kind = "Collapsible box"
            bits = [kind]
            if e.label and e.type not in _NO_LABEL:
                bits.append("\"%s\"" % e.label)
            if e.type == "TEXT_LINES":
                bits.append("lines: %s" % " / ".join(x.strip() for x in e.label.split("|")))
            if e.type in ("ROW", "COLUMN", "BOX", "SPLIT", "GRID") and e.align:
                bits.append("aligned")
            if e.type == "SPLIT":
                bits.append("factor %.2f" % e.split_factor)
            if e.type == "COLOR" and e.use_alpha:
                bits.append("with alpha")
            if e.type in ("ENUM", "MENU"):
                bits.append("options: " + ", ".join(i[1] for i in el.parse_enum_items(e.enum_items)))
            if e.type in ("POINTER", "TEMPLATE_ID"):
                bits.append(el.ID_TYPES[e.id_type][0])
            if e.type == "SEARCH":
                bits.append("searches bpy.data.%s" % e.search_source)
            if e.description:
                bits.append("tooltip: %s" % e.description)
            if e.type == "PANEL" and n.is_panel and n.parent is None:
                bits.append("location: " + el.panel_place(e, self.s).title())
            elif e.type != "PANEL" and e.location != "PANEL":
                bits.append("DRAWN OUTSIDE THE PANEL, in: " + el.LOCATIONS[e.location][0]
                            + (" (%s)" % e.location_note if e.location_note else ""))
            ref = self._ref(n)
            if ref:
                bits.append("-> " + ref)
            mods = [k + "=" + str(v) for k, v in el.layout_attrs(e, d.container)]
            if mods:
                bits.append("[%s]" % ", ".join(mods))
            return " | ".join(bits)

        def rec(nodes, depth):
            for n in nodes:
                lines.append("%s- %s" % ("  " * depth, describe(n)))
                rec(n.children, depth + 1)

        rec(self.roots, 0)
        return "\n".join(lines)

    def location_lines(self):
        lines = []
        for n in self.roots:
            if n.is_panel:
                lines.append("- Panel \"%s\": %s" % (n.elem.label or n.name, el.panel_place(n.elem, self.s).title()))
        for n in self.nodes:
            if n.outside is n:
                lines.append("- \"%s\" is NOT drawn by a panel; it lives in: %s%s" % (
                    n.elem.label or n.name, el.LOCATIONS[n.elem.location][0],
                    " - " + n.elem.location_note if n.elem.location_note else ""))
        return lines or ["- Everything is in the main panel."]

    def _ref(self, n):
        t = n.elem.type
        if t in el.VALUE_ATTR or t in ("POINTER", "TEMPLATE_ID"):
            return "`props.%s`" % n.name
        if t == "LIST":
            return "`props.%s_items` / `props.%s_index`" % (n.name, n.name)
        if t == "BUTTON":
            return "operator `%s.%s`" % (self.prefix, n.name)
        return ""

    def llm(self):
        code = self.python()
        loc = el.PLACEMENTS[self.s.placement][0]
        ops = ["- `%s.%s` — \"%s\"" % (self.prefix, name, label) for name, _, label, _ in self.operators]
        props = []
        for n in self.nodes:
            decl, ctor = self.property_defs(n)
            if ctor:
                props.append("| `props.%s` | %s | %s |" % (n.name, ctor, n.elem.label))
        parts = [
            "# Blender addon task: wire up this UI",
            "",
            "## What I want it to do",
            "",
            "<!-- Describe the behaviour of each control here. -->",
            "",
            "## Context",
            "",
            "- Addon: **%s** (prefix `%s`), minimum Blender %s" % (self.addon_name, self.prefix, self.s.blender_min),
            "- Location: %s%s" % (loc, " > tab \"%s\"" % self.s.category if self.region == "UI" else ""),
            "- All UI state lives in one `PropertyGroup` on the scene: `context.scene.%s`" % self.group,
            "- The UI layout was designed visually; keep it unless I ask for changes.",
            "",
            "## Where things live in the Blender UI",
            "",
        ] + self.location_lines() + [
            "",
            "## UI outline",
            "",
            self.outline() or "(empty)",
            "",
            "## Properties (`context.scene.%s`)" % self.group,
            "",
            "| Property | Type | Label |", "|---|---|---|",
        ] + (props or ["| (none) | | |"]) + [
            "",
            "## Operators to implement",
            "",
        ] + (ops or ["(none)"]) + [
            "",
            "## Generated skeleton",
            "",
            "The `draw` methods are final; the operators are stubs marked `TODO`.",
            "",
            "```python",
            code.rstrip(),
            "```",
            "",
            "## Instructions",
            "",
            "Return one complete, runnable single-file Blender addon. Implement every TODO operator,",
            "read values from `context.scene.%s`, and keep class naming / registration intact." % self.group,
            "",
        ]
        return "\n".join(parts)

    # -- JSON ------------------------------------------------------------------
    def json(self):
        return dump_project(self.s)

    def text(self, fmt):
        return {"PYTHON": self.python, "LLM": self.llm, "JSON": self.json}[fmt]()

    def filename(self, fmt):
        return {"PYTHON": "%s.py" % self.prefix, "LLM": "%s_llm_prompt.md" % self.prefix,
                "JSON": "%s_layout.json" % self.prefix}[fmt]


# -- project (de)serialisation -----------------------------------------------------
_SETTING_KEYS = ("addon_name", "author", "prefix", "blender_min", "placement", "category", "export_format")


def _skip(p):
    return p.identifier in ("rna_type", "selected", "marker") or p.is_readonly or p.type in {"POINTER", "COLLECTION"}


def _element_dict(e):
    out = {}
    for p in e.bl_rna.properties:
        if _skip(p):
            continue
        v = getattr(e, p.identifier)
        if getattr(p, "array_length", 0):
            v = [round(x, 5) for x in v]
            if v == [round(x, 5) for x in p.default_array]:
                continue
        elif p.identifier == "enum_value":
            pass
        elif v == p.default and p.identifier not in ("type", "indent"):
            continue
        out[p.identifier] = v
    return out


def dump_project(s):
    data = {
        "format": "blender-ui-builder",
        "version": FORMAT_VERSION,
        "settings": {k: getattr(s, k) for k in _SETTING_KEYS},
        "elements": [_element_dict(e) for e in s.elements],
    }
    return json.dumps(data, indent=2) + "\n"


def load_project(s, text):
    data = json.loads(text)
    if data.get("format") != "blender-ui-builder":
        raise ValueError("Not a Blender UI Builder project file")
    for k, v in data.get("settings", {}).items():
        if k in _SETTING_KEYS:
            try:
                setattr(s, k, v)
            except (TypeError, ValueError):
                pass
    s.elements.clear()
    with branches.no_sync():
        _load_elements(s, data)
    tree.normalize(s.elements)
    branches.sync_all(s)
    s.active_index = 0


def _load_elements(s, data):
    for item in data.get("elements", []):
        if item.get("type") not in el.DEFS:
            continue
        e = s.elements.add()
        e = s.elements[len(s.elements) - 1]
        e.auto_ident = False  # restore the stored identifier exactly
        # enum_items must be set before enum_value
        ordered = sorted(item.items(), key=lambda kv: kv[0] == "enum_value")
        for k, v in ordered:
            if k not in e.bl_rna.properties or k == "auto_ident":
                continue
            try:
                setattr(e, k, tuple(v) if isinstance(v, list) else v)
            except (TypeError, ValueError, AttributeError):
                pass
        e.auto_ident = item.get("auto_ident", True)
