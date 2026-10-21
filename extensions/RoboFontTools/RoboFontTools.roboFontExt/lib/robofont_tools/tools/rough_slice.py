"""Interactive rough knife for the RoboFont Tools palette."""
from __future__ import annotations

from collections import defaultdict
from math import hypot
from pathlib import Path
from random import Random
import traceback

from AppKit import NSImage
from mojo.events import (
    BaseEventTool, getActiveEventTool, installTool, uninstallTool,
    setActiveEventTool,
)
from mojo.roboFont import CurrentGlyph, RGlyph

from .rough_slice_model import SliceSettings, paired_edges


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


def _plan(glyph, start, end, settings, seed):
    before = _seams(glyph, start, end)
    glyph.slice((start, end), canHaveComponent=False, roundValue=False)
    after = _seams(glyph, start, end)
    pairs = []
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
        edges = paired_edges(first[3], first[4], sides, settings, rng)
        pairs.append((records, sides, edges))
    return pairs


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


def rough_slice(glyph, start, end, settings, seed=None):
    """Cut each crossed contour independently in one undoable glyph edit."""
    settings.validate()
    if glyph is None or hypot(end[0]-start[0], end[1]-start[1]) < 2:
        return 0
    seed = seed if seed is not None else Random().getrandbits(64)
    replacements = []
    count = 0
    # RoboFont's slice handles one contour's two intersections at a time.
    # Isolating each contour also prevents a distant contour from changing the
    # pairing of the current contour's two seam edges.
    for index, contour in enumerate(glyph.contours):
        if contour.open:
            continue
        candidate = RGlyph()
        candidate.appendContour(contour)
        pairs = _plan(candidate, start, end, settings, seed + index)
        if not pairs:
            continue
        _apply_pairs(candidate, pairs)
        replacements.append((index, tuple(candidate.contours)))
        count += len(pairs)
    if not replacements:
        print("Rough Slice: no clean contour crossing")
        return 0
    with glyph.undo("Rough Slice"):
        for index, _contours in reversed(replacements):
            glyph.removeContour(index)
        for _index, contours in replacements:
            for contour in contours:
                glyph.appendContour(contour)
    glyph.changed()
    return count


class RoughSliceEventTool(BaseEventTool):
    title = "Rough Slice"

    def __init__(self, settings_provider, active_callback=None):
        super().__init__()
        self.settings_provider = settings_provider
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
        try:
            count = rough_slice(CurrentGlyph(), start, end, self.settings_provider())
            if count:
                print(f"Rough Slice: cut {count} contour(s)")
        except Exception:
            print("Rough Slice: failed; outline was not changed")
            traceback.print_exc()


class RoughSliceTool:
    content = """
    * TwoColumnForm @roughSliceControl
    > : Rough Slice:
    > (Activate Knife) @roughSliceButton
    > : Spacing (u):
    > [_25_] @roughSliceSpacing
    > : Gap (u):
    > [_20_] @roughSliceGap
    > : Jitter (u):
    > [_30_] @roughSliceJitter
    """
    description_data = {
        "roughSliceControl": {"titleColumnWidth": 120, "itemColumnWidth": 142},
        "roughSliceButton": {"callback": "_roughSliceCallback"},
        "roughSliceSpacing": {"valueType": "number"},
        "roughSliceGap": {"valueType": "number"},
        "roughSliceJitter": {"valueType": "number"},
    }

    def __init__(self, render):
        self._render = render
        self._tool = None
        self._settings_provider = None
        self._active_callback = None

    def set_settings_provider(self, provider):
        self._settings_provider = provider

    def set_active_callback(self, callback):
        self._active_callback = callback

    def _active_changed(self, active):
        if self._active_callback is not None:
            self._active_callback(active)

    def start(self):
        self._tool = RoughSliceEventTool(self._settings_provider, self._active_changed)
        installTool(self._tool)

    def stop(self):
        if self._tool is not None:
            uninstallTool(self._tool)
            self._tool = None

    def refresh(self):
        pass

    def activate(self):
        setActiveEventTool(self._tool.__class__.__name__)
        if getActiveEventTool() is self._tool:
            self._active_changed(True)
            print("Rough Slice: knife active — drag a line across closed contours")
            return True
        print("Rough Slice: could not activate the knife in the current Glyph Editor")
        return False
