from __future__ import annotations

from typing import Callable

from mojo.subscriber import (
    Subscriber,
    registerGlyphEditorSubscriber,
    unregisterGlyphEditorSubscriber,
)

from .selected_points_model import (
    SelectedPointsPresentation,
    presentation_for_glyph,
    selected_contour_points,
)
from .selected_points_state import state


KEY = "com.boryskosmynka.robofonttools.selectedPoints"
DEBUG = True


def _debug(message):
    if DEBUG:
        print(f"Measure Selected Points: {message}")


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
        self.__class__.instances.add(self)
        _debug("attached to glyph editor")
        self._refresh()

    def destroy(self):
        self._hide()
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
            self._hide()
            return
        if glyph is None:
            glyph = self.getGlyphEditor().getGlyph().asFontParts()
        elif hasattr(glyph, "asFontParts"):
            glyph = glyph.asFontParts()
        presentation = presentation_for_glyph(glyph)
        tool = self.__class__.tool
        tool._update_presentation(presentation)
        points = selected_contour_points(glyph)
        _debug(f"selected points = {len(points)}")
        if len(points) != 2:
            self._hide()
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
        _debug("overlay updated")

    def _hide(self):
        if hasattr(self, "layer"):
            self.layer.clearSublayers()

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

class SelectedPointsTool:
    content = """
    * TwoColumnForm @selectedPointsControl
    > : Measure Selected Points:
    > (-X) @selectedPointsEnabled
    * Box @selectedPointsInfoBox
    > * TwoColumnForm @selectedPointsValues
    >> : Distance:
    >> — @selectedPointsDistance
    >> : Δx:
    >> — @selectedPointsDeltaX
    >> : Δy:
    >> — @selectedPointsDeltaY
    >> : Angle:
    >> — @selectedPointsAngle
    """
    description_data = {
        "selectedPointsControl": {"titleColumnWidth": 210, "itemColumnWidth": 52},
        "selectedPointsEnabled": {
            "callback": "_selectedPointsEnabledCallback",
            "value": state.enabled,
        },
        "selectedPointsInfoBox": {"margins": 8},
        "selectedPointsValues": {"titleColumnWidth": 80, "itemColumnWidth": 140},
        "selectedPointsDistance": {"alignment": "right", "width": 140},
        "selectedPointsDeltaX": {"alignment": "right", "width": 140},
        "selectedPointsDeltaY": {"alignment": "right", "width": 140},
        "selectedPointsAngle": {"alignment": "right", "width": 140},
    }

    def __init__(self, render: Callable):
        self._render = render
        self._started = False
        self._presentation = SelectedPointsPresentation()

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

    def _update_presentation(self, presentation):
        if presentation == self._presentation:
            return
        self._presentation = presentation
        self._render(presentation)

    def is_enabled(self):
        return state.enabled

    def set_enabled(self, enabled: bool):
        state.enabled = bool(enabled)
        if state.enabled:
            _debug("enabled")
            self.start()
        else:
            _debug("disabled")
            self._update_presentation(SelectedPointsPresentation())
            for subscriber in tuple(SelectedPointsSubscriber.instances):
                subscriber._hide()
            self.stop()
