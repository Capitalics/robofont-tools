"""Interactive rough knife for the RoboFont Tools palette."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from math import hypot
from pathlib import Path
from random import Random
import traceback

from AppKit import NSImage
from mojo.events import (
    BaseEventTool, getActiveEventTool, installTool, uninstallTool,
    setActiveEventTool,
)
from mojo.roboFont import AllFonts, CurrentGlyph, RGlyph
from mojo.subscriber import (
    Subscriber, registerRoboFontSubscriber, unregisterRoboFontSubscriber,
)

from .base import PaletteTool
from .rough_slice_model import SliceSettings, final_structure, paired_edges


def _xy(point):
    return float(point.x), float(point.y)


def _key(a, b):
    return tuple(sorted(((round(a[0], 4), round(a[1], 4)),
                         (round(b[0], 4), round(b[1], 4)))))


def _seams(glyph, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length < 2:
        return {}
    ux, uy = dx / length, dy / length
    found = defaultdict(list)
    for contour_index, contour in enumerate(glyph.contours):
        if contour.open:
            continue
        points = tuple(contour.points)
        for index, point in enumerate(points):
            following = points[(index + 1) % len(points)]
            a, b = _xy(point), _xy(following)
            if point.type == "offcurve" or following.type != "line":
                continue
            if hypot(b[0]-a[0], b[1]-a[1]) < 2:
                continue
            ta, tb = ((p[0]-start[0])*ux + (p[1]-start[1])*uy for p in (a, b))
            da, db = ((p[0]-start[0])*uy - (p[1]-start[1])*ux for p in (a, b))
            if min(ta, tb) < -0.01 or max(ta, tb) > length + 0.01:
                continue
            if abs(da) > .01 or abs(db) > .01:
                continue
            found[_key(a, b)].append((contour_index, index, (index+1) % len(points), a, b))
    return found


def _side(contour, seam, start, end):
    dx, dy = end[0]-start[0], end[1]-start[1]
    distances = []
    for point in contour.points:
        if point.type == "offcurve" or point in (contour.points[seam[1]], contour.points[seam[2]]):
            continue
        distance = dx * (point.y-start[1]) - dy * (point.x-start[0])
        if abs(distance) > .01:
            distances.append(distance)
    if not distances:
        return 0
    total = sum(distances)
    return 1 if total > 0 else -1 if total < 0 else 0


def _plan(glyph, start, end, settings, seed, forced_intervals=None):
    """Slice ``glyph`` and return (pairs, interval count per pair)."""
    before = _seams(glyph, start, end)
    glyph.slice((start, end), canHaveComponent=False, roundValue=False)
    after = _seams(glyph, start, end)
    pairs = []
    used_intervals = []
    rng = Random(seed)
    for key, records in after.items():
        if key in before or len(records) != 2 or records[0][0] == records[1][0]:
            continue
        first_start, first_end = records[0][3], records[0][4]
        # Classify sides in the seam's own direction: contour point order may
        # run opposite to the dragged line.
        sides = [_side(glyph.contours[r[0]], r, first_start, first_end) for r in records]
        if set(sides) != {-1, 1}:
            continue
        first = records[0]
        forced = None
        if forced_intervals is not None and len(used_intervals) < len(forced_intervals):
            forced = forced_intervals[len(used_intervals)]
        edges = paired_edges(first[3], first[4], sides, settings, rng, forced)
        used_intervals.append(len(edges[1]) - 1)
        pairs.append((records, sides, edges))
    return pairs, used_intervals


def _apply_pairs(glyph, pairs):
    # Apply in descending point-index order when a contour has several seams.
    operations = []
    for records, sides, edges in pairs:
        first = records[0]
        for record, side in zip(records, sides):
            contour_index, first_index, last_index, a, b = record
            positions = edges[side]
            if a != first[3]:
                positions = list(reversed(positions))
            operations.append((contour_index, first_index, last_index, positions))
    for contour_index, first_index, last_index, positions in sorted(
            operations, key=lambda op: (op[0], op[2] if op[2] else 10**9), reverse=True):
        contour = glyph.contours[contour_index]
        old_points = tuple(contour.points)
        first_point, last_point = old_points[first_index], old_points[last_index]
        insertion_index = last_index if last_index else len(old_points)
        for position in reversed(positions[1:-1]):
            contour.insertPoint(insertion_index, position=position, type="line")
        first_point.x, first_point.y = positions[0]
        last_point.x, last_point.y = positions[-1]


def plan_rough_slice(glyph, start, end, settings, seed, forced_intervals=None):
    """Work out the cut without changing ``glyph``.

    Returns (replacements, intervals): replacements is a list of
    (contour index, new contours); intervals maps contour index to the
    point-interval count of each seam, so a second source can match it.
    """
    settings.validate()
    replacements = []
    intervals = {}
    # RoboFont's slice handles one contour's two intersections at a time.
    # Isolating each contour also prevents a distant contour from changing the
    # pairing of the current contour's two seam edges.
    for index, contour in enumerate(glyph.contours):
        if contour.open:
            continue
        candidate = RGlyph()
        candidate.appendContour(contour)
        forced = (forced_intervals or {}).get(index)
        pairs, used = _plan(candidate, start, end, settings, seed + index, forced)
        if not pairs:
            continue
        _apply_pairs(candidate, pairs)
        replacements.append((index, tuple(candidate.contours)))
        intervals[index] = used
    return replacements, intervals


def commit_rough_slice(glyph, replacements):
    with glyph.undo("Rough Slice"):
        for index, _contours in reversed(replacements):
            glyph.removeContour(index)
        for _index, contours in replacements:
            for contour in contours:
                glyph.appendContour(contour)
    glyph.changed()


def _structure(contours):
    return [tuple(point.type for point in contour.points) for contour in contours]


def _final_structure(glyph, replacements):
    return final_structure(
        _structure(glyph.contours),
        [(index, _structure(contours)) for index, contours in replacements])


def rough_slice(glyph, start, end, settings, seed=None):
    """Cut each crossed contour independently in one undoable glyph edit."""
    settings.validate()
    if glyph is None or hypot(end[0]-start[0], end[1]-start[1]) < 2:
        return 0
    seed = seed if seed is not None else Random().getrandbits(64)
    replacements, intervals = plan_rough_slice(glyph, start, end, settings, seed)
    if not replacements:
        print("Rough Slice: no clean contour crossing")
        return 0
    commit_rough_slice(glyph, replacements)
    return sum(len(counts) for counts in intervals.values())


def rough_slice_pair(default_glyph, other_glyph, start, end, settings, seed=None):
    """Make the same cut in two sources, or change neither.

    The default gets gap 0 (pieces touching); the other source gets
    ``settings.gap``. Both use the same random draws and point counts, and the
    results must have matching contour structure so they stay compatible.
    """
    settings.validate()
    if hypot(end[0]-start[0], end[1]-start[1]) < 2:
        return 0
    if _structure(default_glyph.contours) != _structure(other_glyph.contours):
        raise ValueError("the two sources are not compatible before the cut")
    seed = seed if seed is not None else Random().getrandbits(64)
    default_replacements, intervals = plan_rough_slice(
        default_glyph, start, end, replace(settings, gap=0), seed)
    if not default_replacements:
        print("Rough Slice: no clean contour crossing")
        return 0
    other_replacements, other_intervals = plan_rough_slice(
        other_glyph, start, end, settings, seed, forced_intervals=intervals)
    same_contours = ([index for index, _ in default_replacements]
                     == [index for index, _ in other_replacements])
    if (not same_contours or intervals != other_intervals
            or _final_structure(default_glyph, default_replacements)
            != _final_structure(other_glyph, other_replacements)):
        raise ValueError("the cut gives different results in the two sources; "
                         "nothing was changed")
    commit_rough_slice(default_glyph, default_replacements)
    commit_rough_slice(other_glyph, other_replacements)
    return sum(len(counts) for counts in intervals.values())


def _font_key(font):
    """AllFonts may return new wrappers; identify the underlying font."""
    return id(font.naked() if hasattr(font, "naked") else font)


def _font_label(font):
    family = getattr(font.info, "familyName", None) or ""
    style = getattr(font.info, "styleName", None) or ""
    name = f"{family} {style}".strip()
    if not name:
        path = getattr(font, "path", None)
        name = Path(path).stem if path else "Untitled"
    return name


class RoughSliceEventTool(BaseEventTool):
    title = "Rough Slice"

    def __init__(self, cut, active_callback=None):
        super().__init__()
        self.cut = cut
        self.active_callback = active_callback
        self.start_point = None
        self.layer = None
        self._toolbar_icon = None

    def getToolbarIcon(self):
        if self._toolbar_icon is None:
            resource = (Path(__file__).resolve().parents[3] / "resources"
                        / "roughSliceKnife.pdf")
            icon = NSImage.alloc().initWithContentsOfFile_(str(resource))
            if icon is None:
                return super().getToolbarIcon()
            icon.setTemplate_(True)
            self._toolbar_icon = icon
        return self._toolbar_icon

    def getToolbarTip(self):
        return "Rough Slice — drag a line across closed contours"

    def becomeActive(self):
        if self.active_callback is not None:
            self.active_callback(True)

    def becomeInactive(self):
        self.start_point = None
        if self.layer is not None:
            self.layer.clearSublayers()
        if self.active_callback is not None:
            self.active_callback(False)

    def setup(self):
        self.layer = self.extensionContainer(
            identifier="com.boryskosmynka.robofonttools.roughslice.preview",
            location="foreground", clear=True)

    def mouseDown(self, point, clickCount):
        self.start_point = _xy(point)

    def mouseDragged(self, point, delta):
        if self.start_point is None or self.layer is None:
            return
        self.layer.clearSublayers()
        self.layer.appendLineSublayer(startPoint=self.start_point, endPoint=_xy(point),
                                      strokeColor=(1, .25, .25, .9), strokeWidth=2)

    def mouseUp(self, point):
        if self.layer is not None:
            self.layer.clearSublayers()
        start = self.start_point
        self.start_point = None
        if start is None:
            return
        end = _xy(point)
        if hypot(end[0]-start[0], end[1]-start[1]) < 2:
            print("Rough Slice: drag a line across a closed contour; a click alone does not cut")
            return
        self.cut(start, end)


class _FontListWatcher(Subscriber):
    """Keeps the second-source list current as fonts open and close."""

    tool = None

    def fontDocumentDidOpen(self, info):
        if self.__class__.tool is not None:
            self.__class__.tool.refresh_sources()

    def fontDocumentDidClose(self, info):
        if self.__class__.tool is not None:
            self.__class__.tool.refresh_sources()


NO_SECOND_SOURCE = "None (single source)"


class RoughSliceTool(PaletteTool):
    content = """
    ---------------
    !§ Rough Slice
    (Activate Knife) @roughSliceButton
    * TwoColumnForm @roughSliceForm
    > : Second source:
    > (None ...) @roughSliceSecondSource
    * HorizontalStack @roughSliceValues
    > * VerticalStack @roughSliceSpacingColumn
    >> !- Spacing
    >> [_25_] @roughSliceSpacing
    > * VerticalStack @roughSliceGapColumn
    >> !- Gap
    >> [_20_] @roughSliceGap
    > * VerticalStack @roughSliceJitterColumn
    >> !- Jitter
    >> [_30_] @roughSliceJitter
    ---------------
    """

    def __init__(self):
        super().__init__()
        self._tool = None
        self._sources = []

    def descriptions(self):
        field = {"valueType": "number", "width": "fill"}
        return {
            "roughSliceButton": {"callback": lambda sender: self.activate(),
                                 "width": "fill"},
            "roughSliceForm": {"titleColumnWidth": 100, "itemColumnWidth": 162},
            "roughSliceSecondSource": {"items": [NO_SECOND_SOURCE]},
            "roughSliceValues": {"distribution": "fillEqually"},
            "roughSliceSpacing": dict(field, toolTip="Point spacing along the cut (5–50 units)"),
            "roughSliceGap": dict(field, toolTip="Gap between the pieces; 0 = touching. "
                                                 "With a second source, the default gets 0 "
                                                 "and the second source gets this gap."),
            "roughSliceJitter": dict(field, toolTip="Roughness of the cut edge"),
        }

    def start(self):
        self._tool = RoughSliceEventTool(self.cut, self._active_changed)
        installTool(self._tool)
        _FontListWatcher.tool = self
        registerRoboFontSubscriber(_FontListWatcher)
        self.refresh_sources()

    def stop(self):
        _FontListWatcher.tool = None
        unregisterRoboFontSubscriber(_FontListWatcher)
        if self._tool is not None:
            uninstallTool(self._tool)
            self._tool = None

    def refresh(self):
        self.refresh_sources()

    def refresh_sources(self):
        """Rebuild the second-source list, keeping the current choice if open."""
        popup = self.window.getItem("roughSliceSecondSource")
        previous = self.second_source()
        self._sources = [font for font in AllFonts()]
        popup.setItems([NO_SECOND_SOURCE] + [_font_label(font) for font in self._sources])
        popup.set(0)
        if previous is not None:
            for position, font in enumerate(self._sources):
                if _font_key(font) == _font_key(previous):
                    popup.set(position + 1)
                    break

    def second_source(self):
        if self.window is None:
            return None
        position = self.window.getItem("roughSliceSecondSource").get()
        if position is None or position < 1 or position > len(self._sources):
            return None
        return self._sources[position - 1]

    def settings(self):
        return SliceSettings(
            spacing=float(self.window.getItem("roughSliceSpacing").get()),
            gap=float(self.window.getItem("roughSliceGap").get()),
            jitter=float(self.window.getItem("roughSliceJitter").get()),
        )

    def _active_changed(self, active):
        if self.window is None:
            return
        button = self.window.getItem("roughSliceButton")
        button.getNSButton().setTitle_("Knife Active — Drag" if active else "Activate Knife")

    def activate(self):
        try:
            self.settings().validate()
        except (ValueError, TypeError) as error:
            print(f"Rough Slice: {error}")
            return False
        setActiveEventTool(self._tool.__class__.__name__)
        if getActiveEventTool() is self._tool:
            self._active_changed(True)
            print("Rough Slice: knife active — drag a line across closed contours")
            return True
        print("Rough Slice: could not activate the knife in the current Glyph Editor")
        return False

    def cut(self, start, end):
        """Cut the current glyph, and the second source's matching glyph if one is chosen."""
        try:
            settings = self.settings()
            glyph = CurrentGlyph()
            if glyph is None:
                return
            other_font = self.second_source()
            if other_font is None:
                count = rough_slice(glyph, start, end, settings)
            else:
                other_glyph = self._matching_glyph(glyph, other_font)
                if other_glyph is None:
                    return
                count = rough_slice_pair(glyph, other_glyph, start, end, settings)
            if count:
                print(f"Rough Slice: cut {count} contour(s)")
        except ValueError as error:
            print(f"Rough Slice: {error}")
        except Exception:
            print("Rough Slice: failed; outline was not changed")
            traceback.print_exc()

    @staticmethod
    def _matching_glyph(glyph, other_font):
        if glyph.font is not None and _font_key(glyph.font) == _font_key(other_font):
            print("Rough Slice: the second source is the font you are drawing in; "
                  "draw in the default source or pick another second source")
            return None
        layer_name = glyph.layer.name
        if layer_name not in other_font.layerOrder:
            print(f"Rough Slice: {_font_label(other_font)} has no layer '{layer_name}'")
            return None
        layer = other_font.getLayer(layer_name)
        if glyph.name not in layer:
            print(f"Rough Slice: {_font_label(other_font)} has no glyph '{glyph.name}'")
            return None
        return layer[glyph.name]
