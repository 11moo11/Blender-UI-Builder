"""Import the UI of another (enabled) addon into the builder.

Every registered bpy.types.Panel of the chosen addon is "drawn" against a recording
layout that captures the layout calls (row, prop, operator ...). Property types, names,
tooltips, enum options and current values are read from Blender's RNA, so the result
mirrors what the addon really shows.
"""

import inspect
import types

import bpy

from . import elements as el
from .icons import valid_icon

MAX_ITEMS = 3000
MAX_POPOVER_DEPTH = 2


class Item:
    def __init__(self, type_id, label="", **fields):
        self.type = type_id
        self.label = label
        self.fields = fields
        self.children = []


class Ctx:
    def __init__(self, context):
        self.context = context
        self.count = 0
        self.depth = 0
        self.warnings = []


class OpProxy:
    """Swallows property assignments on a returned operator."""

    def __setattr__(self, k, v):
        pass

    def __getattr__(self, k):
        return None


_MODIFIERS = {"enabled": "enabled", "active": "active", "alert": "alert", "scale_x": "scale_x",
              "scale_y": "scale_y", "emboss": "emboss", "alignment": "alignment",
              "use_property_split": "prop_split"}
_LAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())
_LAYOUT_FUNCS = set(bpy.types.UILayout.bl_rna.functions.keys())
_ID_NAMES = {v[0]: k for k, v in el.ID_TYPES.items()}


def _clean_name(name):
    return (name or "").replace(",", " ").strip()


def _icon(v):
    return valid_icon(v) if isinstance(v, str) else None


def _rna_prop(data, name):
    try:
        return data.bl_rna.properties.get(name)
    except AttributeError:
        return None


def _current(data, name):
    try:
        return getattr(data, name)
    except Exception:
        return None


def _enum_info(rna):
    pairs = []
    try:
        for it in rna.enum_items:
            nm = _clean_name(it.name)
            if nm:
                pairs.append((it.identifier, nm))
    except Exception:
        pass
    return pairs[:40]


def _range(rna, fields, integer):
    try:
        lo, hi = rna.soft_min, rna.soft_max
        if abs(lo) < 1e6 and abs(hi) < 1e6:
            fields.update(use_range=True, range_min=float(lo), range_max=float(hi))
    except Exception:
        pass


def item_from_prop(data, name, text, icon, expand, slider, toggle, icon_only, index, force=None):
    """Build an Item for layout.prop(data, name)."""
    rna = _rna_prop(data, name)
    label = text if text is not None else (rna.name if rna else name)
    ident = name
    if rna is None:
        return Item("LABEL", "%s (custom property)" % label, ident=ident)
    f = {"ident": ident, "description": rna.description}
    ic = _icon(icon)
    if ic:
        f["icon"] = ic
    cur = _current(data, name)
    if index >= 0 and cur is not None and not isinstance(cur, str):
        try:
            cur = cur[index]
        except Exception:
            pass
    t, arr = rna.type, getattr(rna, "is_array", False) and index < 0
    n = rna.array_length if arr else 0

    def done(type_id, **extra):
        f.update(extra)
        return Item(type_id, label, **f)

    try:
        if t == "BOOLEAN" and not arr:
            style = "TOGGLE" if toggle in (True, 1) else "CHECKBOX"
            if icon_only or (toggle in (True, 1) and text == "" and ic):
                style = "ICON"
            return done("BOOL", bool_style=style, bool_value=bool(cur))
        if t in ("INT", "FLOAT") and arr:
            sub = rna.subtype
            if sub in ("COLOR", "COLOR_GAMMA") and n in (3, 4):
                return done("COLOR_ALPHA" if n == 4 else "COLOR",
                            **({"color_alpha_value": tuple(cur)} if n == 4 and cur else
                               {"color_value": tuple(cur)[:3]} if cur else {}))
            if sub == "EULER" and n == 3:
                return done("EULER", euler_value=tuple(cur) if cur else (0, 0, 0))
            if n == 2:
                return done("VEC2", vec2_value=tuple(float(x) for x in cur) if cur else (0, 0))
            if n >= 3:
                return done("VEC3", vec3_value=tuple(float(x) for x in cur)[:3] if cur else (0, 0, 0))
        if t == "INT":
            fx = {"int_value": int(cur) if cur is not None else 0}
            _range(rna, fx, True)
            return done("INT", **fx)
        if t == "FLOAT":
            sub = rna.subtype
            v = float(cur) if cur is not None else 0.0
            if sub == "FACTOR":
                return done("FACTOR", factor_value=v)
            if sub == "PERCENTAGE":
                return done("PERCENT", percent_value=v)
            if sub == "ANGLE":
                return done("ANGLE", angle_value=v)
            if sub == "DISTANCE":
                return done("DISTANCE", distance_value=v)
            fx = {}
            _range(rna, fx, False)
            if slider:
                return done("SLIDER", slider_value=min(max(v, 0.0), 1.0), **fx)
            return done("FLOAT", float_value=v, **fx)
        if t == "STRING":
            sub = rna.subtype
            if sub in ("FILE_PATH", "FILE_NAME"):
                return done("FILEPATH", file_value=cur or "")
            if sub == "DIR_PATH":
                return done("DIRPATH", dir_value=cur or "")
            return done("STRING", string_value=cur if isinstance(cur, str) else "")
        if t == "ENUM":
            pairs = _enum_info(rna)
            names = [n_ for _, n_ in pairs] or ["Option A", "Option B"]
            parsed = el.parse_enum_items(", ".join(names))
            fx = {"enum_items": ", ".join(names),
                  "enum_style": "TABS" if force == "TABS" else "EXPAND" if expand else "DROPDOWN"}
            if isinstance(cur, str):
                for (ident_, _), (new_id, _) in zip(pairs, parsed):
                    if ident_ == cur:
                        fx["enum_value"] = new_id
            return done("MENU" if force == "MENU" else "ENUM", **fx)
        if t == "POINTER":
            ft = rna.fixed_type.identifier if rna.fixed_type else ""
            if ft in _ID_NAMES:
                return done("POINTER", id_type=_ID_NAMES[ft])
            f["description"] = (f["description"] + " " if f["description"] else "") + "(original type: %s)" % ft
            return done("POINTER", id_type="OBJECT")
    except Exception as e:  # unusual property: keep the label, don't abort the import
        return Item("LABEL", "%s (%s)" % (label, e.__class__.__name__), ident=ident)
    return Item("LABEL", "%s (%s)" % (label, t.lower()), ident=ident)


class Rec:
    """Recording stand-in for bpy.types.UILayout."""

    def __init__(self, item, ctx):
        object.__setattr__(self, "_item", item)
        object.__setattr__(self, "_ctx", ctx)
        object.__setattr__(self, "_attrs", {})

    # -- attributes ---------------------------------------------------------------
    def __setattr__(self, name, value):
        self._attrs[name] = value
        key = _MODIFIERS.get(name)
        if key:
            self._item.fields[key] = value

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _LAYOUT_PROPS:
            return self._attrs.get(name, {"scale_x": 1.0, "scale_y": 1.0, "enabled": True, "active": True,
                                          "alignment": "EXPAND", "emboss": "NORMAL"}.get(name))
        if name in _LAYOUT_FUNCS:
            return lambda *a, **k: self._generic(name, a, k)
        raise AttributeError(name)

    # -- helpers -------------------------------------------------------------------
    def _add(self, item):
        self._ctx.count += 1
        if self._ctx.count > MAX_ITEMS:
            raise RuntimeError("too many elements; import aborted")
        self._item.children.append(item)
        return item

    def _child(self, type_id, label="", **fields):
        return Rec(self._add(Item(type_id, label, **fields)), self._ctx)

    def _generic(self, name, args, kwargs):
        """Unsupported layout function: leave a visible placeholder."""
        self._add(Item("LABEL", "(%s)" % name))
        if name in ("menu_pie", "split"):
            return self._child("COLUMN")
        return None

    # -- containers ------------------------------------------------------------------
    def row(self, align=False, **kw):
        return self._child("ROW", align=bool(align))

    def column(self, align=False, **kw):
        return self._child("COLUMN", align=bool(align))

    def box(self, **kw):
        return self._child("BOX")

    def split(self, factor=0.0, align=False, **kw):
        return self._child("SPLIT", split_factor=float(factor) or 0.5, align=bool(align))

    def column_flow(self, columns=0, align=False, **kw):
        return self._child("GRID", grid_columns=int(columns), align=bool(align), grid_row_major=False)

    def grid_flow(self, row_major=False, columns=0, even_columns=False, even_rows=False, align=False, **kw):
        return self._child("GRID", grid_columns=int(columns), grid_row_major=bool(row_major),
                           grid_even_columns=bool(even_columns), grid_even_rows=bool(even_rows),
                           align=bool(align))

    def panel(self, idname, default_closed=False):
        header = Rec(Item("ROW"), self._ctx)  # header contents are discarded
        body = self._child("COLLAPSE", idname.replace("_", " ").title(), ident=idname,
                           expanded=not default_closed)
        return header, body

    def panel_prop(self, data, prop, **kw):
        rna = _rna_prop(data, prop)
        header = Rec(Item("ROW"), self._ctx)
        body = self._child("COLLAPSE", rna.name if rna else prop, ident=prop)
        return header, body

    # -- content -----------------------------------------------------------------------
    def label(self, text="", icon="NONE", **kw):
        ic = _icon(icon)
        if text or ic:
            f = {"icon": ic} if ic else {}
            self._add(Item("LABEL", text, **f))

    def separator(self, factor=1.0, type="AUTO"):
        style = type if type in ("AUTO", "SPACE", "LINE") else "AUTO"
        self._add(Item("SEPARATOR", "", separator_style=style, spacer_factor=float(factor)))

    def separator_spacer(self):
        self._add(Item("SEPARATOR", "", separator_style="SPACE"))

    def prop(self, data, property, text=None, icon="NONE", expand=False, slider=False, toggle=-1,
             icon_only=False, index=-1, **kw):
        self._add(item_from_prop(data, property, text, icon, expand, slider, toggle, icon_only, index))

    def props_enum(self, data, property, **kw):
        self._add(item_from_prop(data, property, None, "NONE", True, False, -1, False, -1))

    def prop_menu_enum(self, data, property, text=None, icon="NONE", **kw):
        self._add(item_from_prop(data, property, text, icon, False, False, -1, False, -1, force="MENU"))

    def prop_tabs_enum(self, data, property, **kw):
        self._add(item_from_prop(data, property, None, "NONE", False, False, -1, False, -1, force="TABS"))

    def prop_search(self, data, property, search_data, search_property, text=None, icon="NONE", **kw):
        rna = _rna_prop(data, property)
        label = text if text is not None else (rna.name if rna else property)
        src = search_property if search_property in el.SEARCH_SOURCES else "objects"
        f = {"ident": property, "search_source": src, "description": rna.description if rna else ""}
        if _icon(icon):
            f["icon"] = _icon(icon)
        self._add(Item("SEARCH", label, **f))

    def prop_enum(self, data, property, value, text=None, icon="NONE", **kw):
        self._add(Item("LABEL", text if text is not None else str(value)))

    def prop_decorator(self, *a, **k):
        pass

    def operator(self, operator, text=None, text_ctxt="", translate=True, icon="NONE", **kw):
        name, desc = text, ""
        try:
            mod, fn = operator.split(".", 1)
            rna = getattr(getattr(bpy.ops, mod), fn).get_rna_type()
            name = text if text is not None else rna.name
            desc = rna.description
        except Exception:
            name = text if text is not None else operator
        f = {"ident": operator.replace(".", "_"),
             "description": ("Calls %s. %s" % (operator, desc)).strip()}
        if _icon(icon):
            f["icon"] = _icon(icon)
        self._add(Item("BUTTON", name or "", **f))
        return OpProxy()

    def operator_menu_enum(self, operator, property, text=None, icon="NONE", **kw):
        self.operator(operator, text, icon=icon)
        return OpProxy()

    def operator_enum(self, operator, property, **kw):
        self._add(Item("LABEL", "(operator_enum %s)" % operator))

    def menu(self, menu, text=None, icon="NONE", **kw):
        cls = getattr(bpy.types, menu, None)
        label = text if text is not None else (getattr(cls, "bl_label", None) or menu)
        names = []
        if cls is not None and self._ctx.depth < MAX_POPOVER_DEPTH:
            sub = Item("COLUMN")
            self._ctx.depth += 1
            try:
                record_class(cls, self._ctx, sub)
            except Exception:
                pass
            self._ctx.depth -= 1
            names = [_clean_name(i.label) for i in _flatten(sub) if i.type in ("BUTTON", "LABEL") and i.label]
        f = {"ident": menu, "enum_items": ", ".join(names[:30]) or "Option A, Option B"}
        if _icon(icon):
            f["icon"] = _icon(icon)
        self._add(Item("MENU", label, **f))

    def menu_contents(self, menu):
        self.menu(menu)

    def popover(self, panel, text=None, icon="NONE", **kw):
        cls = getattr(bpy.types, panel, None)
        label = text if text is not None else (getattr(cls, "bl_label", None) or panel)
        f = {"ident": panel}
        if _icon(icon):
            f["icon"] = _icon(icon)
        item = self._add(Item("POPOVER", label, **f))
        if cls is not None and self._ctx.depth < MAX_POPOVER_DEPTH:
            self._ctx.depth += 1
            try:
                record_class(cls, self._ctx, item)
            except Exception:
                pass
            self._ctx.depth -= 1

    def template_list(self, listtype_name, list_id, dataptr, propname, active_dataptr, active_propname,
                      rows=5, **kw):
        rna = _rna_prop(dataptr, propname)
        self._add(Item("LIST", rna.name if rna else propname, ident=propname,
                       list_rows=max(1, min(int(rows), 20))))

    def template_ID(self, data, property, **kw):
        rna = _rna_prop(data, property)
        ft = rna.fixed_type.identifier if rna and rna.fixed_type else ""
        self._add(Item("TEMPLATE_ID", rna.name if rna else property, ident=property,
                       id_type=_ID_NAMES.get(ft, "OBJECT")))

    def template_color_picker(self, data, property, **kw):
        rna = _rna_prop(data, property)
        self._add(Item("COLOR_PICKER", rna.name if rna else property, ident=property))

    def template_icon_view(self, data, property, **kw):
        self._add(item_from_prop(data, property, None, "NONE", True, False, -1, False, -1))

    def progress(self, factor=0.0, type="BAR", text="", **kw):
        self._add(Item("PROGRESS", text, progress_factor=min(max(float(factor), 0.0), 1.0),
                       progress_type=type if type in ("BAR", "RING") else "BAR"))

    def context_pointer_set(self, *a, **k):
        pass

    def context_string_set(self, *a, **k):
        pass


def _flatten(item):
    for c in item.children:
        yield c
        yield from _flatten(c)


class _FakeSelf:
    """Stands in for `self` in Panel.draw: class attributes and helper methods still work."""

    def __init__(self, cls, layout):
        self.__dict__["_cls"] = cls
        self.__dict__["layout"] = layout

    def __getattr__(self, name):
        cls = self._cls
        if name == "is_popover":
            return False
        try:
            raw = inspect.getattr_static(cls, name)
        except AttributeError:
            if name == "bl_idname":  # Blender derives it from the class name
                return cls.__name__
            raise
        if isinstance(raw, types.FunctionType):  # plain method: bind to the stand-in
            return types.MethodType(raw, self)
        return getattr(cls, name)  # staticmethod / classmethod / data attribute

    def __setattr__(self, k, v):
        self.__dict__[k] = v


def record_class(cls, ctx, root_item, method="draw"):
    fn = getattr(cls, method, None)
    if fn is None:
        return
    fn(_FakeSelf(cls, Rec(root_item, ctx)), ctx.context)


# -- scanning & committing ---------------------------------------------------------------------
def addon_panels(module):
    """Registered Panel classes defined by `module` (or its submodules)."""
    out = []
    for cls in bpy.types.Panel.__subclasses__():
        mod = getattr(cls, "__module__", "") or ""
        if (mod == module or mod.startswith(module + ".")) and getattr(cls, "is_registered", False):
            out.append(cls)
    return out


def addon_modules(exclude=()):
    """[(module name, display name, panel count)] for enabled addons that register panels."""
    prefs = bpy.context.preferences.addons
    counts = {}
    for cls in bpy.types.Panel.__subclasses__():
        mod = getattr(cls, "__module__", "") or ""
        if getattr(cls, "is_registered", False):
            counts[mod] = counts.get(mod, 0) + 1
    result = []
    for key in prefs.keys():
        if key in exclude:
            continue
        n = sum(c for m, c in counts.items() if m == key or m.startswith(key + "."))
        if n:
            result.append((key, addon_display_name(key), n))
    return sorted(result, key=lambda r: r[1].lower())


def addon_display_name(module):
    import sys
    mod = sys.modules.get(module)
    info = getattr(mod, "bl_info", None) or {}
    name = info.get("name")
    if not name:
        try:
            import addon_utils
            name = (addon_utils.module_bl_info(mod) or {}).get("name") if mod else None
        except Exception:
            name = None
    return name or module.split(".")[-1]


def build_panel(cls, ctx):
    """Item tree for one panel class. Returns (item, error_message or '')."""
    opts = getattr(cls, "bl_options", set())
    item = Item("PANEL", getattr(cls, "bl_label", "") or cls.__name__,
                default_closed="DEFAULT_CLOSED" in opts)
    error = ""
    if hasattr(cls, "draw_header"):
        try:
            head = Item("ROW")
            record_class(cls, ctx, head, "draw_header")
            if head.children and head.children[0].type == "BOOL":
                item.fields["header_checkbox"] = True
        except Exception:
            pass
    try:
        record_class(cls, ctx, item)
    except Exception as e:
        error = "%s: %s" % (e.__class__.__name__, e)
    return item, error


def commit(s, items, new_element, normalize):
    """Append Item trees to the builder's element list."""
    def add(item, depth):
        e = new_element(s, item.type, len(s.elements), depth, item.label)
        e.auto_ident = False
        fields = dict(item.fields)
        if "ident" in fields:
            e.ident = el.slugify(fields.pop("ident"))
        order = sorted(fields.items(), key=lambda kv: kv[0] == "enum_value")
        for k, v in order:
            try:
                setattr(e, k, v)
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
        for c in item.children:
            add(c, depth + 1)

    for it in items:
        add(it, 0)
    normalize(s.elements)
