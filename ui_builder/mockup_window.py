"""Open the mockup next to the builder: in its own window or in a split of the current area."""

import bpy


def _show_mockup(area):
    """Turn an area into a Properties editor on the Scene tab, where the mockup panel is listed first."""
    area.type = "PROPERTIES"
    space = area.spaces.active
    try:
        space.context = "SCENE"
    except TypeError:
        pass
    area.tag_redraw()


def _window_region(area):
    return next((r for r in area.regions if r.type == "WINDOW"), None)


class UIB_OT_mockup_window(bpy.types.Operator):
    """Open the mockup preview in a separate window you can move to another monitor or place beside Blender"""
    bl_idname = "ui_builder.mockup_window"
    bl_label = "Mockup in New Window"

    @classmethod
    def poll(cls, context):
        return context.area is not None

    def execute(self, context):
        wm = context.window_manager
        before = set(w.as_pointer() for w in wm.windows)
        area = context.area
        try:
            with context.temp_override(area=area, region=_window_region(area) or context.region):
                bpy.ops.wm.window_new()
        except RuntimeError as e:
            self.report({"ERROR"}, "Could not open a window: %s" % e)
            return {"CANCELLED"}
        new = [w for w in wm.windows if w.as_pointer() not in before]
        if not new or not new[0].screen.areas:
            self.report({"WARNING"}, "The window opened, but its area could not be found")
            return {"CANCELLED"}
        _show_mockup(new[0].screen.areas[0])
        return {"FINISHED"}


class UIB_OT_mockup_split(bpy.types.Operator):
    """Split this area in two and show the mockup preview in the new half, so builder and mockup are side by side"""
    bl_idname = "ui_builder.mockup_split"
    bl_label = "Mockup Beside Builder"

    direction: bpy.props.EnumProperty(items=[("VERTICAL", "Side by side", ""), ("HORIZONTAL", "Stacked", "")],
                                      default="VERTICAL", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.screen is not None

    def execute(self, context):
        screen, area = context.screen, context.area
        before = set(a.as_pointer() for a in screen.areas)
        try:
            with context.temp_override(area=area, region=_window_region(area) or context.region):
                bpy.ops.screen.area_split(direction=self.direction, factor=0.5)
        except RuntimeError as e:
            self.report({"ERROR"}, "Could not split the area: %s" % e)
            return {"CANCELLED"}
        new = [a for a in screen.areas if a.as_pointer() not in before]
        if not new:
            self.report({"WARNING"}, "The area was split, but the new half could not be found")
            return {"CANCELLED"}
        _show_mockup(new[0])
        return {"FINISHED"}


classes = (UIB_OT_mockup_window, UIB_OT_mockup_split)
