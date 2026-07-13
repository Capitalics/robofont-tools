from __future__ import annotations

"""Development-only cubic intersection and subdivision proof utilities.

These functions deliberately do not participate in production generation.
They establish the source-curve parameter provenance needed by a later hybrid
fragment reconstruction phase.
"""

from dataclasses import dataclass
import math

from fracturize.model import CubicSegment, LineSegment, Point, SourceContour


@dataclass(frozen=True)
class CubicIntersection:
    segment_index: int
    t: float
    line_t: float
    point: Point
    proxy_t: float
    refinement_error: float


def cubic_point(segment: CubicSegment, t: float) -> Point:
    inverse = 1.0 - t
    weights = (
        inverse**3,
        3.0 * inverse**2 * t,
        3.0 * inverse * t**2,
        t**3,
    )
    points = (segment.start, segment.control1, segment.control2, segment.end)
    return (
        sum(weight * point[0] for weight, point in zip(weights, points, strict=True)),
        sum(weight * point[1] for weight, point in zip(weights, points, strict=True)),
    )


def cubic_derivative(segment: CubicSegment, t: float) -> Point:
    inverse = 1.0 - t
    return (
        3.0 * inverse**2 * (segment.control1[0] - segment.start[0])
        + 6.0 * inverse * t * (segment.control2[0] - segment.control1[0])
        + 3.0 * t**2 * (segment.end[0] - segment.control2[0]),
        3.0 * inverse**2 * (segment.control1[1] - segment.start[1])
        + 6.0 * inverse * t * (segment.control2[1] - segment.control1[1])
        + 3.0 * t**2 * (segment.end[1] - segment.control2[1]),
    )


def split_cubic(segment: CubicSegment, t: float) -> tuple[CubicSegment, CubicSegment]:
    """Split a cubic exactly with de Casteljau subdivision."""

    if not 0.0 <= t <= 1.0:
        raise ValueError("cubic split parameter must be in 0..1")

    def interpolate(first: Point, second: Point) -> Point:
        return (
            first[0] + (second[0] - first[0]) * t,
            first[1] + (second[1] - first[1]) * t,
        )

    p01 = interpolate(segment.start, segment.control1)
    p12 = interpolate(segment.control1, segment.control2)
    p23 = interpolate(segment.control2, segment.end)
    p012 = interpolate(p01, p12)
    p123 = interpolate(p12, p23)
    split_point = interpolate(p012, p123)
    return (
        CubicSegment(segment.start, p01, p012, split_point),
        CubicSegment(split_point, p123, p23, segment.end),
    )


def split_cubic_many(segment: CubicSegment, parameters) -> tuple[CubicSegment, ...]:
    """Split at ordered original-curve parameters without parameter drift."""

    ordered = sorted({float(value) for value in parameters if 0.0 < value < 1.0})
    if any(not math.isfinite(value) for value in ordered):
        raise ValueError("cubic split parameters must be finite")
    pieces = []
    remaining = segment
    previous = 0.0
    for parameter in ordered:
        if parameter <= previous:
            continue
        local_parameter = (parameter - previous) / (1.0 - previous)
        left, remaining = split_cubic(remaining, local_parameter)
        pieces.append(left)
        previous = parameter
    pieces.append(remaining)
    return tuple(pieces)


def _cross(first: Point, second: Point) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _subtract(first: Point, second: Point) -> Point:
    return (first[0] - second[0], first[1] - second[1])


def _distance_to_chord(point: Point, start: Point, end: Point) -> float:
    direction = _subtract(end, start)
    length = math.hypot(*direction)
    if length == 0.0:
        return math.dist(point, start)
    return abs(_cross(_subtract(point, start), direction)) / length


def _proxy_samples(segment: CubicSegment, tolerance: float):
    samples = []

    def recurse(current: CubicSegment, start_t: float, end_t: float, depth: int):
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
        middle_t = (start_t + end_t) * 0.5
        recurse(left, start_t, middle_t, depth + 1)
        recurse(right, middle_t, end_t, depth + 1)

    recurse(segment, 0.0, 1.0, 0)
    return tuple(samples)


def _line_segment_intersection(first_start, first_end, second_start, second_end):
    first_direction = _subtract(first_end, first_start)
    second_direction = _subtract(second_end, second_start)
    denominator = _cross(first_direction, second_direction)
    if abs(denominator) <= 1e-15:
        return None
    delta = _subtract(second_start, first_start)
    first_t = _cross(delta, second_direction) / denominator
    second_t = _cross(delta, first_direction) / denominator
    epsilon = 1e-12
    if -epsilon <= first_t <= 1.0 + epsilon and -epsilon <= second_t <= 1.0 + epsilon:
        return (
            min(1.0, max(0.0, first_t)),
            min(1.0, max(0.0, second_t)),
        )
    return None


def _refine_parameter(
    segment: CubicSegment,
    line: LineSegment,
    lower: float,
    upper: float,
    guess: float,
    tolerance: float,
) -> tuple[float, float]:
    direction = _subtract(line.end, line.start)
    line_length = math.hypot(*direction)

    def function(parameter):
        return _cross(_subtract(cubic_point(segment, parameter), line.start), direction)

    low_value = function(lower)
    high_value = function(upper)
    parameter = guess
    for _ in range(80):
        value = function(parameter)
        distance = abs(value) / line_length
        if distance <= tolerance:
            return parameter, distance
        if low_value == 0.0:
            return lower, 0.0
        if high_value == 0.0:
            return upper, 0.0
        if low_value * value <= 0.0:
            upper = parameter
            high_value = value
        else:
            lower = parameter
            low_value = value
        derivative = cubic_derivative(segment, parameter)
        derivative_value = _cross(derivative, direction)
        candidate = (
            parameter - value / derivative_value
            if abs(derivative_value) > 1e-18
            else (lower + upper) * 0.5
        )
        if not lower < candidate < upper:
            candidate = (lower + upper) * 0.5
        parameter = candidate
    distance = abs(function(parameter)) / line_length
    if distance > tolerance:
        raise ValueError("line/cubic intersection refinement did not converge")
    return parameter, distance


def intersect_cubic_with_line(
    segment: CubicSegment,
    line: LineSegment,
    *,
    proxy_tolerance: float = 0.25,
    refinement_tolerance: float = 1e-10,
) -> tuple[CubicIntersection, ...]:
    """Find transverse finite-line intersections and refine their cubic `t`."""

    direction = _subtract(line.end, line.start)
    length_squared = direction[0] ** 2 + direction[1] ** 2
    if length_squared == 0.0:
        raise ValueError("fracture line must have non-zero length")
    if proxy_tolerance <= 0.0 or refinement_tolerance <= 0.0:
        raise ValueError("intersection tolerances must be positive")

    candidates = []
    samples = _proxy_samples(segment, proxy_tolerance)
    for (start_t, start), (end_t, end) in zip(samples, samples[1:]):
        crossing = _line_segment_intersection(start, end, line.start, line.end)
        if crossing is None:
            continue
        proxy_fraction, _ = crossing
        proxy_t = start_t + (end_t - start_t) * proxy_fraction
        parameter, error = _refine_parameter(
            segment,
            line,
            start_t,
            end_t,
            proxy_t,
            refinement_tolerance,
        )
        point = cubic_point(segment, parameter)
        line_t = (
            (point[0] - line.start[0]) * direction[0]
            + (point[1] - line.start[1]) * direction[1]
        ) / length_squared
        if -1e-10 <= line_t <= 1.0 + 1e-10:
            candidates.append(
                CubicIntersection(
                    segment_index=-1,
                    t=parameter,
                    line_t=min(1.0, max(0.0, line_t)),
                    point=point,
                    proxy_t=proxy_t,
                    refinement_error=error,
                )
            )

    unique = []
    for candidate in sorted(candidates, key=lambda item: item.t):
        if unique and abs(candidate.t - unique[-1].t) <= 1e-9:
            if candidate.refinement_error < unique[-1].refinement_error:
                unique[-1] = candidate
            continue
        unique.append(candidate)
    return tuple(unique)


def intersect_contour_with_line(
    contour: SourceContour,
    line: LineSegment,
    **kwargs,
) -> tuple[CubicIntersection, ...]:
    intersections = []
    for segment_index, segment in enumerate(contour.segments):
        if not isinstance(segment, CubicSegment):
            continue
        intersections.extend(
            CubicIntersection(
                segment_index=segment_index,
                t=item.t,
                line_t=item.line_t,
                point=item.point,
                proxy_t=item.proxy_t,
                refinement_error=item.refinement_error,
            )
            for item in intersect_cubic_with_line(segment, line, **kwargs)
        )
    return tuple(sorted(intersections, key=lambda item: (item.segment_index, item.t)))


def split_contour_at_intersections(
    contour: SourceContour,
    intersections: tuple[CubicIntersection, ...],
):
    """Return source-ordered exact pieces; only intersection nodes are added."""

    by_segment = {}
    for intersection in intersections:
        by_segment.setdefault(intersection.segment_index, []).append(intersection.t)
    pieces = []
    for index, segment in enumerate(contour.segments):
        parameters = by_segment.get(index, ())
        if isinstance(segment, CubicSegment):
            pieces.extend(split_cubic_many(segment, parameters))
        elif parameters:
            raise ValueError("Phase 1 proof only splits cubic source segments")
        else:
            pieces.append(segment)
    return tuple(pieces)


def maximum_reconstruction_error(
    original: CubicSegment,
    pieces: tuple[CubicSegment, ...],
    parameters,
    *,
    samples: int = 1001,
) -> float:
    boundaries = (0.0, *sorted(parameters), 1.0)
    maximum = 0.0
    for index in range(samples):
        parameter = index / (samples - 1)
        piece_index = min(
            len(pieces) - 1,
            next(
                (item for item in range(len(pieces)) if parameter <= boundaries[item + 1]),
                len(pieces) - 1,
            ),
        )
        start = boundaries[piece_index]
        end = boundaries[piece_index + 1]
        local = 0.0 if end == start else (parameter - start) / (end - start)
        maximum = max(
            maximum,
            math.dist(cubic_point(original, parameter), cubic_point(pieces[piece_index], local)),
        )
    return maximum
