from __future__ import annotations

import AppKit

from mojo.subscriber import (
    Subscriber,
    registerGlyphEditorSubscriber,
    unregisterGlyphEditorSubscriber,
)

from .base import PaletteTool
from .selected_points_model import (
    presentation_for_glyph,
    selected_contour_points,
)
from .selected_points_state import state


KEY = "com.boryskosmynka.robofonttools.selectedPoints"
DEBUG = False
HUD_WIDTH = 220
HUD_HEIGHT = 92
HUD_BOTTOM_INSET = 16


def _debug(message):
    if DEBUG:
        print(f"Measure Selected Points: {message}")


class SelectedPointsHUD:
    """A native view-space status panel owned by one Glyph Editor."""

    def __init__(self, glyph_view, glyph_editor):
        if hasattr(glyph_view, "getNSView"):
            glyph_view = glyph_view.getNSView()
        self.document_view = glyph_view
        self.scroll_view = self.document_view.enclosingScrollView()
        if self.scroll_view is None:
            raise RuntimeError("Measure Selected Points: glyph view has no scroll view")
        self.clip_view = self.scroll_view.contentView()
        self.glyph_editor = glyph_editor
        width = HUD_WIDTH
        height = HUD_HEIGHT
        self._preferred_size = (width, height)
        self.view = AppKit.NSView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, width, height)
        )
        self.view.setWantsLayer_(True)
        layer = self.view.layer()
        layer.setBackgroundColor_(
            AppKit.NSColor.colorWithWhite_alpha_(0.90, 0.35).CGColor()
        )
        layer.setCornerRadius_(8)
        layer.setMasksToBounds_(True)
        self._value_fields = {}
        self._build_content()
        self.clip_view.addSubview_(self.view)
        self._notification_center = AppKit.NSNotificationCenter.defaultCenter()
        self.clip_view.setPostsBoundsChangedNotifications_(True)
        self.clip_view.setPostsFrameChangedNotifications_(True)
        self._notification_center.addObserver_selector_name_object_(
            self,
            "clipViewBoundsDidChange:",
            AppKit.NSViewBoundsDidChangeNotification,
            self.clip_view,
        )
        self._notification_center.addObserver_selector_name_object_(
            self,
            "clipViewFrameDidChange:",
            AppKit.NSViewFrameDidChangeNotification,
            self.clip_view,
        )
        self._position_in_viewport()
        self.hide("initial state")

    def _build_content(self):
        rows = (
            ("Distance", "distance"),
            ("Δx", "delta_x"),
            ("Δy", "delta_y"),
            ("Angle", "angle"),
        )
        for index, (title, key) in enumerate(rows):
            y = HUD_HEIGHT - 24 - index * 18
            label = AppKit.NSTextField.labelWithString_(title)
            label.setFrame_(AppKit.NSMakeRect(12, y, 74, 16))
            label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
            label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            self.view.addSubview_(label)
            value = AppKit.NSTextField.labelWithString_("—")
            value.setFrame_(AppKit.NSMakeRect(88, y, HUD_WIDTH - 100, 16))
            value.setAlignment_(AppKit.NSTextAlignmentRight)
            value.setFont_(AppKit.NSFont.systemFontOfSize_weight_(
                11, AppKit.NSFontWeightMedium
            ))
            value.setTextColor_(AppKit.NSColor.labelColor())
            self.view.addSubview_(value)
            self._value_fields[key] = value

    def show(self, presentation):
        self._value_fields["distance"].setStringValue_(presentation.distance)
        self._value_fields["delta_x"].setStringValue_(presentation.delta_x)
        self._value_fields["delta_y"].setStringValue_(presentation.delta_y)
        self._value_fields["angle"].setStringValue_(presentation.angle)
        self.view.setHidden_(False)
        _debug("HUD shown")

    def hide(self, reason):
        self.view.setHidden_(True)
        _debug(f"HUD hidden: {reason}")

    def _position_in_viewport(self):
        visible = self.clip_view.bounds()
        preferred_width, preferred_height = self._preferred_size
        width = min(preferred_width, max(visible.size.width - 20, 1))
        height = min(preferred_height, max(visible.size.height - 20, 1))
        x = visible.origin.x + (visible.size.width - width) / 2
        if self.clip_view.isFlipped():
            y = visible.origin.y + max(
                visible.size.height - HUD_BOTTOM_INSET - height, 0
            )
        else:
            y = visible.origin.y + HUD_BOTTOM_INSET
        self.view.setFrame_(AppKit.NSMakeRect(x, y, width, height))

    def clipViewBoundsDidChange_(self, _notification):
        self._position_in_viewport()
        _debug("HUD repositioned: clip-view bounds changed")

    def clipViewFrameDidChange_(self, _notification):
        self._position_in_viewport()
        _debug("HUD repositioned: clip-view frame changed")

    def destroy(self):
        self._notification_center.removeObserver_name_object_(
            self, AppKit.NSViewBoundsDidChangeNotification, self.clip_view
        )
        self._notification_center.removeObserver_name_object_(
            self, AppKit.NSViewFrameDidChangeNotification, self.clip_view
        )
        self.view.removeFromSuperview()


class SelectedPointsSubscriber(Subscriber):
    """Draw a measurement for exactly two selected contour points."""

    tool = None
    instances = set()
    glyphEditorDidSetGlyphDelay = 0
    glyphEditorGlyphDidChangeDelay = 0
    glyphEditorGlyphDidChangeSelectionDelay = 0
    glyphEditorDidScaleDelay = 0

    def build(self):
        self.container = self.getGlyphEditor().extensionContainer(
            identifier=KEY, location="foreground", clear=True
        )
        self.layer = self.container
        self._editor_scale = 1.0
        self.hud = SelectedPointsHUD(
            self.getGlyphEditor().getGlyphView(), self.getGlyphEditor()
        )
        self.__class__.instances.add(self)
        _debug("attached to glyph editor")
        _debug(f"subscriber = {self!r}")
        _debug(f"glyph editor = {self.getGlyphEditor()!r}")
        _debug(
            "active glyph = "
            f"{getattr(self.getGlyphEditor().getGlyph(), 'name', '?')!r}"
        )
        _debug(f"HUD container = {self.hud.clip_view!r}")
        self._refresh()

    def destroy(self):
        self._hide("editor closed")
        self.hud.destroy()
        self.__class__.instances.discard(self)

    def glyphEditorDidSetGlyph(self, info):
        self._refresh(info.get("glyph"))

    def glyphEditorGlyphDidChange(self, info):
        self._refresh(info.get("glyph"))

    def glyphEditorGlyphDidChangeSelection(self, info):
        self._refresh(info.get("glyph"))

    def glyphEditorDidScale(self, info):
        self._editor_scale = max(float(info.get("scale", 1.0)), 0.01)
        self._refresh()

    def _refresh(self, glyph=None):
        if self.__class__.tool is None or not state.enabled:
            self._hide("tool disabled")
            return
        if glyph is None:
            glyph = self.getGlyphEditor().getGlyph().asFontParts()
        elif hasattr(glyph, "asFontParts"):
            glyph = glyph.asFontParts()
        presentation = presentation_for_glyph(glyph)
        points = selected_contour_points(glyph)
        _debug(f"selected points = {len(points)}")
        if len(points) != 2:
            self._hide(f"selection count = {len(points)}")
            return
        first = (float(points[0].x), float(points[0].y))
        second = (float(points[1].x), float(points[1].y))
        _debug(f"p1={first}, p2={second}")
        _debug(
            "dx=" + presentation.delta_x
            + ", dy=" + presentation.delta_y
            + ", distance=" + presentation.distance
        )
        self._draw(first, second)
        self.hud.show(presentation)
        _debug("overlay updated")

    def _hide(self, reason):
        if hasattr(self, "layer"):
            self.layer.clearSublayers()
        if hasattr(self, "hud"):
            self.hud.hide(reason)

    def _draw(self, first, second):
        self.layer.clearSublayers()
        primary = (0.25, 0.55, 0.95, 0.9)
        self.layer.appendLineSublayer(
            startPoint=first,
            endPoint=second,
            strokeColor=primary,
            strokeWidth=self._glyph_units(1),
        )

    def _glyph_units(self, screen_points):
        return screen_points / self._editor_scale


class SelectedPointsTool(PaletteTool):
    content = """
    * TwoColumnForm @selectedPointsControl
    > : Measure Selected Points:
    > (-X) @selectedPointsEnabled
    """

    def __init__(self):
        super().__init__()
        self._started = False

    def descriptions(self):
        return {
            "selectedPointsControl": {"titleColumnWidth": 210, "itemColumnWidth": 52},
            "selectedPointsEnabled": {
                "callback": self._enabled_callback,
                "value": state.enabled,
            },
        }

    def _enabled_callback(self, sender):
        self.set_enabled(sender.get())

    def start(self):
        if self._started or not state.enabled:
            return
        SelectedPointsSubscriber.tool = self
        registerGlyphEditorSubscriber(SelectedPointsSubscriber)
        self._started = True
        _debug("subscriber registered")

    def stop(self):
        if not self._started:
            return
        SelectedPointsSubscriber.tool = None
        unregisterGlyphEditorSubscriber(SelectedPointsSubscriber)
        self._started = False
        _debug("subscriber unregistered")

    def refresh(self):
        for subscriber in tuple(SelectedPointsSubscriber.instances):
            subscriber._refresh()

    def is_enabled(self):
        return state.enabled

    def set_enabled(self, enabled: bool):
        state.enabled = bool(enabled)
        if state.enabled:
            _debug("enabled")
            self.start()
        else:
            _debug("disabled")
            for subscriber in tuple(SelectedPointsSubscriber.instances):
                subscriber._hide("tool disabled")
            self.stop()
