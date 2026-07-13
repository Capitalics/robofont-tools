from __future__ import annotations

"""Exact source-curve intersection and subdivision used by hybrid outlines."""

from dataclasses import dataclass
import math

from .model import CubicSegment, LineSegment, Point


@dataclass(frozen=True)
class CurveIntersection:
    t: float
    line_t: float
    point: Point
    tangent: bool = False


def cubic_point(segment: CubicSegment, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * segment.start[0]
        + 3 * u * u * t * segment.control1[0]
        + 3 * u * t * t * segment.control2[0]
        + t**3 * segment.end[0],
        u**3 * segment.start[1]
        + 3 * u * u * t * segment.control1[1]
        + 3 * u * t * t * segment.control2[1]
        + t**3 * segment.end[1],
    )


def cubic_derivative(segment: CubicSegment, t: float) -> Point:
    u = 1.0 - t
    return (
        3 * u * u * (segment.control1[0] - segment.start[0])
        + 6 * u * t * (segment.control2[0] - segment.control1[0])
        + 3 * t * t * (segment.end[0] - segment.control2[0]),
        3 * u * u * (segment.control1[1] - segment.start[1])
        + 6 * u * t * (segment.control2[1] - segment.control1[1])
        + 3 * t * t * (segment.end[1] - segment.control2[1]),
    )


def split_cubic(segment: CubicSegment, t: float):
    if not 0.0 <= t <= 1.0:
        raise ValueError("cubic split parameter must be in 0..1")

    def lerp(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    p01 = lerp(segment.start, segment.control1)
    p12 = lerp(segment.control1, segment.control2)
    p23 = lerp(segment.control2, segment.end)
    p012 = lerp(p01, p12)
    p123 = lerp(p12, p23)
    point = lerp(p012, p123)
    return (
        CubicSegment(segment.start, p01, p012, point),
        CubicSegment(point, p123, p23, segment.end),
    )


def split_cubic_many(segment: CubicSegment, parameters) -> tuple[CubicSegment, ...]:
    ordered = sorted({float(value) for value in parameters if 0.0 < value < 1.0})
    pieces = []
    remaining = segment
    previous = 0.0
    for parameter in ordered:
        if not math.isfinite(parameter):
            raise ValueError("cubic split parameters must be finite")
        local = (parameter - previous) / (1.0 - previous)
        left, remaining = split_cubic(remaining, local)
        pieces.append(left)
        previous = parameter
    pieces.append(remaining)
    return tuple(pieces)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _line_intersection(first: LineSegment, second: LineSegment):
    a = _sub(first.end, first.start)
    b = _sub(second.end, second.start)
    denominator = _cross(a, b)
    if abs(denominator) <= 1e-14:
        return None
    delta = _sub(second.start, first.start)
    first_t = _cross(delta, b) / denominator
    second_t = _cross(delta, a) / denominator
    epsilon = 1e-10
    if -epsilon <= first_t <= 1 + epsilon and -epsilon <= second_t <= 1 + epsilon:
        return min(1.0, max(0.0, first_t)), min(1.0, max(0.0, second_t))
    return None


def _distance_to_chord(point, start, end):
    direction = _sub(end, start)
    length = math.hypot(*direction)
    return math.dist(point, start) if length == 0 else abs(_cross(_sub(point, start), direction)) / length


def _proxy_samples(segment, tolerance):
    samples = []

    def recurse(current, start_t, end_t, depth):
        flatness = max(
            _distance_to_chord(current.control1, current.start, current.end),
            _distance_to_chord(current.control2, current.start, current.end),
        )
        if flatness <= tolerance or depth >= 30:
            if not samples:
                samples.append((start_t, current.start))
            samples.append((end_t, current.end))
            return
        left, right = split_cubic(current, 0.5)
        middle = (start_t + end_t) * 0.5
        recurse(left, start_t, middle, depth + 1)
        recurse(right, middle, end_t, depth + 1)

    recurse(segment, 0.0, 1.0, 0)
    return tuple(samples)


def intersect_line_with_line(source: LineSegment, cutter: LineSegment):
    result = _line_intersection(source, cutter)
    if result is None:
        return ()
    t, line_t = result
    point = (
        source.start[0] + (source.end[0] - source.start[0]) * t,
        source.start[1] + (source.end[1] - source.start[1]) * t,
    )
    return (CurveIntersection(t, line_t, point),)


def intersect_cubic_with_line(
    segment: CubicSegment,
    line: LineSegment,
    *,
    proxy_tolerance: float,
    refinement_tolerance: float = 1e-10,
):
    """Find finite transverse intersections and refine them on the cubic."""

    direction = _sub(line.end, line.start)
    line_length = math.hypot(*direction)
    if line_length == 0:
        raise ValueError("fracture line has zero length")
    def function(t):
        return _cross(_sub(cubic_point(segment, t), line.start), direction)

    candidates = []
    samples = _proxy_samples(segment, proxy_tolerance)
    for (low, start), (high, end) in zip(samples, samples[1:]):
        crossing = _line_intersection(LineSegment(start, end), line)
        if crossing is None:
            continue
        proxy_fraction, _ = crossing
        guess = low + (high - low) * proxy_fraction
        low_value = function(low)
        high_value = function(high)
        t = guess
        for _ in range(80):
            value = function(t)
            if abs(value) / line_length <= refinement_tolerance:
                break
            if low_value * value <= 0.0:
                high = t
                high_value = value
            else:
                low = t
                low_value = value
            derivative = cubic_derivative(segment, t)
            derivative_value = _cross(derivative, direction)
            candidate = t - value / derivative_value if abs(derivative_value) > 1e-18 else (low + high) * 0.5
            t = candidate if low < candidate < high else (low + high) * 0.5
        point = cubic_point(segment, t)
        length_squared = direction[0] ** 2 + direction[1] ** 2
        line_t = (
            (point[0] - line.start[0]) * direction[0]
            + (point[1] - line.start[1]) * direction[1]
        ) / length_squared
        if not -1e-9 <= line_t <= 1 + 1e-9:
            continue
        derivative = cubic_derivative(segment, t)
        tangent = abs(_cross(derivative, direction)) <= max(
            math.hypot(*derivative) * line_length * 1e-8, 1e-10
        )
        candidates.append(
            CurveIntersection(t, min(1.0, max(0.0, line_t)), point, tangent)
        )
    unique = []
    for candidate in sorted(candidates, key=lambda item: item.t):
        if unique and abs(candidate.t - unique[-1].t) <= 1e-7:
            continue
        unique.append(candidate)
    return tuple(unique)


def split_line_many(segment: LineSegment, parameters) -> tuple[LineSegment, ...]:
    values = (0.0, *sorted({float(v) for v in parameters if 0 < v < 1}), 1.0)
    points = tuple(
        (
            segment.start[0] + (segment.end[0] - segment.start[0]) * value,
            segment.start[1] + (segment.end[1] - segment.start[1]) * value,
        )
        for value in values
    )
    return tuple(LineSegment(a, b) for a, b in zip(points, points[1:]))
