"""Pure geometry for Contour Probe.

Curves are adaptively flattened once per outline change. This deliberately
trades a tiny approximation (0.25 units maximum chord error) for predictable
mouse-move performance and keeps all editor objects out of this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

Point = tuple[float, float]
EPSILON = 1e-8


@dataclass(frozen=True)
class ProbeInterval:
    """One consecutive region bounded by neighbouring probe intersections."""
    start: Point
    end: Point
    start_distance: float
    end_distance: float
    is_filled: bool

    @property
    def thickness(self) -> float:
        return abs(self.end_distance - self.start_distance)

    @property
    def midpoint(self) -> Point:
        return (
            (self.start[0] + self.end[0]) / 2,
            (self.start[1] + self.end[1]) / 2,
        )


@dataclass(frozen=True)
class MeasurementResult:
    anchor: Point
    nearest_point: Point
    tangent: Point
    normal: Point
    primary: ProbeInterval
    secondary: ProbeInterval | None
    intervals: tuple[ProbeInterval, ...]

    # Compatibility aliases for the original single-interval caller.
    @property
    def intersection_a(self) -> Point:
        return self.primary.start

    @property
    def intersection_b(self) -> Point:
        return self.primary.end

    @property
    def thickness(self) -> float:
        return self.primary.thickness


@dataclass(frozen=True)
class OutlineCache:
    contours: tuple[tuple[Point, ...], ...]
    edges: tuple[tuple[Point, Point], ...]


def _point(value) -> Point:
    return (float(value[0]), float(value[1]))


def _distance_to_line(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length < EPSILON:
        return hypot(point[0] - start[0], point[1] - start[1])
    return abs(dx * (start[1] - point[1]) - (start[0] - point[0]) * dy) / length


def _cubic_point(points: tuple[Point, Point, Point, Point], t: float) -> Point:
    a, b, c, d = points
    mt = 1.0 - t
    return (
        mt ** 3 * a[0] + 3 * mt * mt * t * b[0] + 3 * mt * t * t * c[0] + t ** 3 * d[0],
        mt ** 3 * a[1] + 3 * mt * mt * t * b[1] + 3 * mt * t * t * c[1] + t ** 3 * d[1],
    )


def _flatten_cubic(points, tolerance=0.25, depth=0) -> tuple[Point, ...]:
    a, b, c, d = points
    if depth >= 12 or max(_distance_to_line(b, a, d), _distance_to_line(c, a, d)) <= tolerance:
        return (a, d)
    ab = ((a[0]+b[0])/2, (a[1]+b[1])/2); bc = ((b[0]+c[0])/2, (b[1]+c[1])/2)
    cd = ((c[0]+d[0])/2, (c[1]+d[1])/2); abc = ((ab[0]+bc[0])/2, (ab[1]+bc[1])/2)
    bcd = ((bc[0]+cd[0])/2, (bc[1]+cd[1])/2); mid = ((abc[0]+bcd[0])/2, (abc[1]+bcd[1])/2)
    left = _flatten_cubic((a, ab, abc, mid), tolerance, depth + 1)
    right = _flatten_cubic((mid, bcd, cd, d), tolerance, depth + 1)
    return left[:-1] + right


def _flatten_quadratic(points, tolerance=0.25, depth=0) -> tuple[Point, ...]:
    a, b, c = points
    if depth >= 12 or _distance_to_line(b, a, c) <= tolerance:
        return (a, c)
    ab = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    bc = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)
    mid = ((ab[0] + bc[0]) / 2, (ab[1] + bc[1]) / 2)
    left = _flatten_quadratic((a, ab, mid), tolerance, depth + 1)
    right = _flatten_quadratic((mid, bc, c), tolerance, depth + 1)
    return left[:-1] + right


def _flatten_qcurve(start: Point, controls: tuple[Point, ...], end: Point | None) -> tuple[Point, ...]:
    """Flatten FontParts qcurve controls, including implied on-curve points."""
    if not controls:
        return ()
    if end is None:
        # A closed all-offcurve qcurve is rare. Its implicit start/end is the
        # midpoint of the final and first controls.
        end = ((controls[-1][0] + controls[0][0]) / 2, (controls[-1][1] + controls[0][1]) / 2)
        start = end
    points = [start]
    current = start
    for index, control in enumerate(controls):
        target = end if index == len(controls) - 1 else (
            (control[0] + controls[index + 1][0]) / 2,
            (control[1] + controls[index + 1][1]) / 2,
        )
        piece = _flatten_quadratic((current, control, target))
        points.extend(piece[1:])
        current = target
    return tuple(points)


def cache_from_contours(contours) -> OutlineCache:
    """Build a closed native-contour cache from FontParts contour segments."""
    flattened = []
    for contour in contours:
        if getattr(contour, "open", False):
            continue
        segments = tuple(contour.segments)
        if not segments:
            continue
        path = []
        # A FontParts segment stores its ending on-curve (and any handles),
        # not its starting on-curve. The previous segment supplies that start.
        previous = segments[-1].onCurve
        if previous is None:
            continue
        for segment in segments:
            start = (float(previous.x), float(previous.y))
            end = None if segment.onCurve is None else (
                float(segment.onCurve.x), float(segment.onCurve.y)
            )
            handles = tuple((float(p.x), float(p.y)) for p in segment.offCurve)
            if segment.type == "line":
                if end is None:
                    continue
                piece = (start, end)
            elif segment.type == "curve" and len(handles) == 2:
                if end is None:
                    continue
                piece = _flatten_cubic((start, handles[0], handles[1], end))
            elif segment.type == "qcurve":
                piece = _flatten_qcurve(start, handles, end)
            else:
                # UFO cubic outlines require two handles. Ignore malformed
                # segments rather than producing an unreliable measurement.
                continue
            path.extend(piece if not path else piece[1:])
            if segment.onCurve is not None:
                previous = segment.onCurve
        if len(path) > 2:
            if hypot(path[0][0]-path[-1][0], path[0][1]-path[-1][1]) > EPSILON:
                path.append(path[0])
            flattened.append(tuple(path))
    edges = tuple((a, b) for path in flattened for a, b in zip(path, path[1:]))
    return OutlineCache(tuple(flattened), edges)


def _nearest_on_edge(anchor: Point, start: Point, end: Point):
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared < EPSILON:
        return None
    t = max(0.0, min(1.0, ((anchor[0]-start[0])*dx + (anchor[1]-start[1])*dy) / squared))
    point = (start[0] + t * dx, start[1] + t * dy)
    return hypot(anchor[0]-point[0], anchor[1]-point[1]), point, (dx, dy)


def nearest_contour_distance(cache: OutlineCache, anchor: Point) -> float | None:
    """Return the nearest cached-outline distance for integration diagnostics."""
    distances = (
        candidate[0]
        for start, end in cache.edges
        if (candidate := _nearest_on_edge(anchor, start, end)) is not None
    )
    return min(distances, default=None)


def _inside_nonzero(point: Point, edges) -> bool:
    winding = 0
    x, y = point
    for (x1, y1), (x2, y2) in edges:
        if y1 <= y < y2 and (x2-x1) * (y-y1) - (x-x1) * (y2-y1) > 0:
            winding += 1
        elif y2 <= y < y1 and (x2-x1) * (y-y1) - (x-x1) * (y2-y1) < 0:
            winding -= 1
    return winding != 0


def measure_contour_probe(cache: OutlineCache, anchor: Point) -> MeasurementResult | None:
    nearest = None
    for start, end in cache.edges:
        candidate = _nearest_on_edge(anchor, start, end)
        if candidate and (nearest is None or candidate[0] < nearest[0]):
            nearest = candidate
    if nearest is None:
        return None
    _, nearest_point, tangent = nearest
    length = hypot(*tangent)
    if length < EPSILON:
        return None
    normal = (-tangent[1] / length, tangent[0] / length)
    intersections = []
    for start, end in cache.edges:
        ex, ey = end[0] - start[0], end[1] - start[1]
        denominator = normal[0] * ey - normal[1] * ex
        if abs(denominator) < EPSILON:
            continue
        rx, ry = start[0] - nearest_point[0], start[1] - nearest_point[1]
        distance = (rx * ey - ry * ex) / denominator
        edge_t = (rx * normal[1] - ry * normal[0]) / denominator
        if -EPSILON <= edge_t <= 1.0 + EPSILON:
            intersections.append(distance)
    intersections.sort()
    unique = []
    for value in intersections:
        if not unique or abs(value - unique[-1]) > 1e-5:
            unique.append(value)
    if len(unique) < 2:
        return None
    intervals = []
    for left, right in zip(unique, unique[1:]):
        midpoint = ((left+right)/2)
        sample = (nearest_point[0] + normal[0]*midpoint, nearest_point[1] + normal[1]*midpoint)
        start = (nearest_point[0] + normal[0]*left, nearest_point[1] + normal[1]*left)
        end = (nearest_point[0] + normal[0]*right, nearest_point[1] + normal[1]*right)
        intervals.append(
            ProbeInterval(start, end, left, right, _inside_nonzero(sample, cache.edges))
        )
    if not intervals:
        return None
    cursor_distance = (
        (anchor[0] - nearest_point[0]) * normal[0]
        + (anchor[1] - nearest_point[1]) * normal[1]
    )

    def distance_to_interval(interval: ProbeInterval) -> float:
        if interval.start_distance <= cursor_distance <= interval.end_distance:
            return 0.0
        return min(
            abs(cursor_distance - interval.start_distance),
            abs(cursor_distance - interval.end_distance),
        )

    primary_index = min(
        range(len(intervals)), key=lambda index: distance_to_interval(intervals[index])
    )
    primary = intervals[primary_index]
    adjacent = [
        index for index in (primary_index - 1, primary_index + 1)
        if 0 <= index < len(intervals)
        and intervals[index].is_filled != primary.is_filled
    ]
    secondary = None
    if adjacent:
        secondary = intervals[min(adjacent, key=lambda index: distance_to_interval(intervals[index]))]
    return MeasurementResult(
        anchor, nearest_point, tangent, normal, primary, secondary, tuple(intervals)
    )
