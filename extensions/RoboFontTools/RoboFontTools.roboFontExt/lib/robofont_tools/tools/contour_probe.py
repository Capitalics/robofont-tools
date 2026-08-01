from __future__ import annotations

from time import monotonic
import traceback
from typing import Callable

import AppKit

from mojo.subscriber import Subscriber, registerGlyphEditorSubscriber, unregisterGlyphEditorSubscriber

from ..geometry import format_number
from .contour_probe_model import (
    cache_from_contours,
    measure_contour_probe,
    nearest_contour_distance,
)
from .contour_probe_state import state

KEY = "com.boryskosmynka.robofonttools.contourProbe"
DEBUG = True
DEBUG_INTERVAL = 1.0


def _debug(message):
    if DEBUG:
        print(f"Contour Probe: {message}")


class ContourProbeSubscriber(Subscriber):
    tool = None
    instances = set()
    glyphEditorDidMouseMoveDelay = 0
    glyphEditorDidSetGlyphDelay = 0
    glyphEditorGlyphDidChangeDelay = 0

    def build(self):
        try:
            self.container = self.getGlyphEditor().extensionContainer(
                identifier=KEY, location="foreground", clear=True
            )
            # Draw directly in the visible extension container. This is the
            # smallest verified Merz pattern and avoids a zero-sized
            # intermediate base layer becoming a clipping parent.
            self.layer = self.container
            _debug(
                "drawing container created; "
                f"subscriber={self!r}; glyph editor={self.getGlyphEditor()!r}; "
                f"container={self.container!r}"
            )
        except Exception:
            print("Contour Probe: drawing container setup failed")
            traceback.print_exc()
            raise
        self.cache = None
        self.glyph = None
        self._editor_scale = self._container_scale()
        self._drawn_layers = {}
        self._last_debug_at = 0.0
        self._rebuild(None)
        self.__class__.instances.add(self)
        _debug("attached to glyph editor")

    def destroy(self):
        if hasattr(self, "layer"):
            self.layer.clearSublayers()
        self.cache = None
        self.__class__.instances.discard(self)

    def _draw_attachment_test(self):
        """Short-lived, unmistakable proof that the foreground container works."""
        if not DEBUG:
            return
        color = (1.0, 0.25, 0.25, 0.8)
        self.layer.appendLineSublayer(
            startPoint=(0, 0), endPoint=(500, 500),
            strokeColor=color, strokeWidth=8,
        )
        self.test_line_layer = self.layer.getSublayers()[-1]
        self.layer.appendTextLineSublayer(
            position=(250, 260), text="Contour Probe test", font="system",
            weight="bold", pointSize=12, fillColor=color,
        )
        self.test_label_layer = self.layer.getSublayers()[-1]
        self.layer.appendOvalSublayer(
            position=(-5, -5), size=(10, 10), fillColor=color,
        )
        self.layer.appendOvalSublayer(
            position=(495, 495), size=(10, 10), fillColor=color,
        )
        _debug(
            "fixed test overlay drawn; "
            f"line={self.test_line_layer!r}; "
            f"visible={self.test_line_layer.getVisible()}; "
            f"stroke={self.test_line_layer.getStrokeColor()}; "
            f"strokeWidth={self.test_line_layer.getStrokeWidth()}"
        )

    def glyphEditorDidSetGlyph(self, info):
        glyph = info.get("glyph")
        _debug(f"glyph changed to {getattr(glyph, 'name', '?')}")
        self._rebuild(glyph)

    def glyphEditorGlyphDidChange(self, info):
        self._rebuild(info.get("glyph"))

    def glyphEditorDidScale(self, info):
        self._editor_scale = max(float(info.get("scale", 1.0)), 0.01)

    def glyphEditorDidMouseMove(self, info):
        tool = self.__class__.tool
        if tool is None or not state.enabled:
            self._hide()
            return
        glyph_point = tuple(info["locationInGlyph"])
        # Draw the marker before considering geometry/cache validity. This is
        # the integration proof: it must follow the cursor on every editor.
        if self.cache is None:
            self._debug_mouse(info, glyph_point)
            self._draw(None, glyph_point)
            return
        self._debug_mouse(info, glyph_point)
        try:
            result = measure_contour_probe(self.cache, glyph_point)
        except Exception:
            print("Contour Probe: measurement failed")
            traceback.print_exc()
            result = None
        self._draw(result, glyph_point)

    def _rebuild(self, glyph):
        try:
            self.glyph = glyph or self.getGlyphEditor().getGlyph().asFontParts()
            # Components are intentionally unsupported: native contours only.
            self.cache = None if self.glyph.components else cache_from_contours(self.glyph.contours)
        except Exception:
            print("Contour Probe: cache rebuild failed")
            traceback.print_exc()
            self.cache = None
        if DEBUG:
            contours = tuple(getattr(self.glyph, "contours", ()))
            closed = sum(not getattr(contour, "open", False) for contour in contours)
            edge_count = len(self.cache.edges) if self.cache else 0
            _debug(f"contours available: {len(contours)}; closed: {closed}; edges cached: {edge_count}")
            self._debug_segment_structure(contours)
        self._hide()
        # RoboFont sends a set-glyph event immediately after subscriber build.
        # Draw after the resulting clear so the test overlay remains visible.
        self._draw_attachment_test()

    def _debug_segment_structure(self, contours):
        """Report the actual FontParts segment shape once per rebuild."""
        if not contours:
            return
        contour = contours[0]
        try:
            segments = tuple(contour.segments)
            _debug(
                "contour[0]="
                f"{type(contour).__name__}; open={contour.open}; "
                f"points={len(contour.points)}; segments={len(segments)}"
            )
            for index, segment in enumerate(segments):
                points = tuple(segment.points)
                coordinates = tuple((point.x, point.y, point.type) for point in points)
                _debug(
                    f"segment[{index}]={type(segment).__name__}; "
                    f"type={segment.type}; points={len(points)}; {coordinates}"
                )
        except Exception:
            print("Contour Probe: segment diagnostics failed")
            traceback.print_exc()

    def _debug_mouse(self, info, glyph_point):
        now = monotonic()
        if now - self._last_debug_at < DEBUG_INTERVAL:
            return
        self._last_debug_at = now
        event = info.get("NSEvent")
        try:
            editor_point = tuple(event.locationInWindow()) if event is not None else None
        except Exception:
            editor_point = None
        _debug(f"mouse editor={editor_point}; glyph={glyph_point}")
        distance = (
            nearest_contour_distance(self.cache, glyph_point)
            if self.cache is not None
            else None
        )
        _debug(f"nearest contour distance = {distance!r}; threshold = none")
        _debug("1. mouse event received; 2. glyph resolved; "
               f"3. contours available: {len(getattr(self.glyph, 'contours', ()))}")

    def _hide(self):
        self.layer.clearSublayers()
        self._drawn_layers.clear()

    def _draw(self, result, cursor):
        self.layer.clearSublayers()
        # The marker establishes that mouse events, glyph-space coordinates and
        # the foreground Merz container work even when geometry returns None.
        if DEBUG:
            self.layer.appendOvalSublayer(
                position=(cursor[0] - 3, cursor[1] - 3), size=(6, 6),
                fillColor=(1.0, 0.25, 0.25, 0.85),
            )
        if result is None:
            return
        self._draw_interval(
            result.primary, color=(0.25, 0.55, 0.95, 0.9),
            stroke_width=2, marker_size=6, point_size=11, weight="bold",
            role="primary",
        )
        if result.secondary is not None:
            self._draw_interval(
                result.secondary, color=(0.48, 0.48, 0.50, 0.7),
                stroke_width=1, marker_size=4, point_size=9, weight="regular",
                role="secondary",
            )
        if DEBUG:
            secondary = "none" if result.secondary is None else f"{result.secondary.thickness:.2f}"
            _debug(
                f"6. intervals found: {len(result.intervals)}; "
                f"7. primary={result.primary.thickness:.2f}, secondary={secondary}; "
                "8. overlay updated"
            )

    def _draw_interval(self, interval, color, stroke_width, marker_size, point_size, weight, role):
        line_layer = self.layer.appendLineSublayer(
            startPoint=interval.start, endPoint=interval.end,
            strokeColor=color, strokeWidth=stroke_width,
        )
        radius = marker_size / 2
        marker_layers = []
        for point in (interval.start, interval.end):
            marker_layers.append(self.layer.appendOvalSublayer(
                position=(point[0] - radius, point[1] - radius),
                size=(marker_size, marker_size), fillColor=color,
            ))
        label = format_number(interval.thickness)
        pill_width, pill_height, pill_radius = self._pill_size(
            label, point_size, weight
        )
        midpoint = interval.midpoint
        pill_layer = self.layer.appendBaseSublayer(
            position=(midpoint[0] - pill_width / 2, midpoint[1] - pill_height / 2),
            size=(pill_width, pill_height),
            backgroundColor=self._pill_color(color),
            borderColor=color,
            borderWidth=self._glyph_units(1),
            cornerRadius=pill_radius,
        )
        text_layer = self.layer.appendTextLineSublayer(
            position=midpoint, text=label, font="system", weight=weight,
            pointSize=point_size, fillColor=(1, 1, 1, 1),
            pointSizeIsVisuallyConstant=True,
            horizontalAlignment="center", verticalAlignment="center",
        )
        self._drawn_layers[role] = dict(
            line=line_layer, markers=tuple(marker_layers), pill_background=pill_layer,
            pill_border=pill_layer, text=text_layer,
        )

    def _container_scale(self):
        """Return the live foreground-container scale used by Merz."""
        try:
            return max(float(self.container.getContainerScale()), 0.01)
        except Exception:
            return getattr(self, "_editor_scale", 1.0)

    def _screen_to_container(self, screen_points):
        """Convert a screen-space dimension to foreground-container units."""
        return screen_points / self._container_scale()

    def _glyph_units(self, screen_points):
        """Backward-compatible name for screen-to-container conversion."""
        return self._screen_to_container(screen_points)

    def _pill_size(self, text, point_size, weight):
        font_weight = (
            AppKit.NSFontWeightBold if weight == "bold"
            else AppKit.NSFontWeightRegular
        )
        font = AppKit.NSFont.systemFontOfSize_weight_(point_size, font_weight)
        attributed = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            text, {AppKit.NSFontAttributeName: font}
        )
        text_width, text_height = attributed.size()
        horizontal_padding = 6
        vertical_padding = 3
        pill_width = text_width + horizontal_padding * 2
        pill_height = text_height + vertical_padding * 2
        return (
            self._screen_to_container(pill_width),
            self._screen_to_container(pill_height),
            self._screen_to_container(pill_height / 2),
        )

    @staticmethod
    def _pill_color(color):
        red, green, blue, _alpha = color
        return (red, green, blue, 0.96)


class ContourProbeTool:
    content = """
    * TwoColumnForm @contourProbeControl
    > : Contour Probe:
    > (-X) @contourProbeEnabled
    """
    description_data = {
        "contourProbeControl": {"titleColumnWidth": 210, "itemColumnWidth": 52},
        "contourProbeEnabled": {
            "callback": "_contourProbeEnabledCallback",
            "value": state.enabled,
        },
    }

    def __init__(self, render: Callable):
        self._render = render
        self._started = False

    def start(self):
        if self._started or not state.enabled:
            return
        try:
            ContourProbeSubscriber.tool = self
            registerGlyphEditorSubscriber(ContourProbeSubscriber)
            self._started = True
            _debug("subscriber registered")
        except Exception:
            ContourProbeSubscriber.tool = None
            raise

    def stop(self):
        if not self._started:
            return
        ContourProbeSubscriber.tool = None
        unregisterGlyphEditorSubscriber(ContourProbeSubscriber)
        self._started = False
        _debug("subscriber unregistered")

    def refresh(self):
        pass

    def is_enabled(self):
        return state.enabled

    def set_enabled(self, enabled: bool):
        state.enabled = bool(enabled)
        if state.enabled:
            _debug("enabled")
            self.start()
        else:
            _debug("disabled")
            for subscriber in tuple(ContourProbeSubscriber.instances):
                subscriber._hide()
            self.stop()
