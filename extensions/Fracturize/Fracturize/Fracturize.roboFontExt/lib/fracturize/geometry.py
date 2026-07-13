from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union
from shapely.validation import explain_validity

from .model import (
    CubicSegment,
    GlyphOutline,
    LineSegment,
    MasterContour,
    NormalizationDiagnostics,
    Point as XY,
)

MAX_CROSS_TOLERANCE_NORMALIZED_DIFFERENCE = 0.002


class UnsupportedOutlineError(ValueError):
    """Raised when an outline is outside the declared polygonal input contract."""


def adaptive_flattening_tolerance(units_per_em: float) -> float:
    """UPM-relative tolerance, clamped to avoid impractical extremes."""

    if units_per_em <= 0:
        raise UnsupportedOutlineError("units per em must be positive")
    return max(0.25, min(1.0, units_per_em / 2000.0))


def _distance_to_line(point: XY, start: XY, end: XY) -> float:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    denominator = math.hypot(dx, dy)
    if denominator == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / denominator


def _midpoint(a: XY, b: XY) -> XY:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def flatten_cubic(
    start: XY,
    control1: XY,
    control2: XY,
    end: XY,
    tolerance: float,
    *,
    _depth: int = 0,
) -> list[XY]:
    """Flatten a cubic adaptively with recursive de Casteljau subdivision."""

    flatness = max(
        _distance_to_line(control1, start, end),
        _distance_to_line(control2, start, end),
    )
    if flatness <= tolerance or _depth >= 24:
        return [start, end]

    p01 = _midpoint(start, control1)
    p12 = _midpoint(control1, control2)
    p23 = _midpoint(control2, end)
    p012 = _midpoint(p01, p12)
    p123 = _midpoint(p12, p23)
    midpoint = _midpoint(p012, p123)

    left = flatten_cubic(start, p01, p012, midpoint, tolerance, _depth=_depth + 1)
    right = flatten_cubic(midpoint, p123, p23, end, tolerance, _depth=_depth + 1)
    return left[:-1] + right


def flatten_outline(outline: GlyphOutline, tolerance: float) -> tuple[tuple[XY, ...], ...]:
    if outline.components:
        names = ", ".join(outline.components)
        raise UnsupportedOutlineError(
            f"components require decomposition before polygonal generation: {names}"
        )
    if not outline.contours:
        raise UnsupportedOutlineError("outline has no contours")

    rings: list[tuple[XY, ...]] = []
    for contour_index, contour in enumerate(outline.contours):
        if not contour.closed:
            raise UnsupportedOutlineError(f"contour {contour_index} is open")
        if not contour.segments:
            raise UnsupportedOutlineError(f"contour {contour_index} is empty")

        points: list[XY] = []
        expected_start = contour.segments[0].start
        for segment_index, segment in enumerate(contour.segments):
            if segment.start != expected_start:
                raise UnsupportedOutlineError(
                    f"contour {contour_index} has a discontinuity at segment {segment_index}"
                )
            if isinstance(segment, LineSegment):
                flattened = [segment.start, segment.end]
            elif isinstance(segment, CubicSegment):
                flattened = flatten_cubic(
                    segment.start,
                    segment.control1,
                    segment.control2,
                    segment.end,
                    tolerance,
                )
            else:  # pragma: no cover - defensive for future segment types
                raise UnsupportedOutlineError(f"unsupported segment type: {type(segment)!r}")
            if points:
                points.extend(flattened[1:])
            else:
                points.extend(flattened)
            expected_start = segment.end

        if points[-1] != points[0]:
            raise UnsupportedOutlineError(f"contour {contour_index} is not geometrically closed")
        points.pop()  # Store rings without a duplicate closing coordinate.
        if len(points) < 3 or len(set(points)) < 3:
            raise UnsupportedOutlineError(f"contour {contour_index} is degenerate")
        rings.append(tuple(points))
    return tuple(rings)


def signed_area(ring: Sequence[XY]) -> float:
    return 0.5 * sum(
        ring[index][0] * ring[(index + 1) % len(ring)][1]
        - ring[(index + 1) % len(ring)][0] * ring[index][1]
        for index in range(len(ring))
    )


def _winding_number(point: XY, ring: Sequence[XY]) -> int:
    x, y = point
    winding = 0
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        if start[1] <= y:
            if end[1] > y and (end[0] - start[0]) * (y - start[1]) - (x - start[0]) * (
                end[1] - start[1]
            ) > 0:
                winding += 1
        elif end[1] <= y and (end[0] - start[0]) * (y - start[1]) - (x - start[0]) * (
            end[1] - start[1]
        ) < 0:
            winding -= 1
    return winding


def _resolve_filled_faces(rings: Sequence[Sequence[XY]], *, allow_self_intersections: bool):
    linework = []
    for index, ring in enumerate(rings):
        if len(ring) < 3:
            raise UnsupportedOutlineError(f"ring {index} has fewer than three points")
        closed = list(ring) + [ring[0]]
        line = LineString(closed)
        if not line.is_simple and not allow_self_intersections:
            raise UnsupportedOutlineError(f"ring {index} self-intersects")
        linework.append(line)

    noded = unary_union(linework)
    faces = list(polygonize(noded))
    selected = []
    evenodd_selected = []
    winds = []
    for face in faces:
        sample = face.representative_point()
        winding = sum(_winding_number((sample.x, sample.y), ring) for ring in rings)
        winds.append(winding)
        if winding != 0:
            selected.append(face)
        if abs(winding) % 2 == 1:
            evenodd_selected.append(face)
    result = unary_union(selected)
    if result.is_empty:
        raise UnsupportedOutlineError("non-zero fill produced an empty silhouette")
    if not result.is_valid:
        raise UnsupportedOutlineError(f"normalized silhouette is invalid: {explain_validity(result)}")
    if not isinstance(result, (Polygon, MultiPolygon)):
        raise UnsupportedOutlineError(f"unexpected normalized geometry: {result.geom_type}")
    evenodd = unary_union(evenodd_selected)
    details = {
        "face_count": len(faces),
        "selected_count": len(selected),
        "winds": tuple(sorted(winds)),
        "evenodd_area": evenodd.area,
    }
    return result, details


def visible_filled_union(rings: Sequence[Sequence[XY]]):
    """Return the non-zero-winding visible union of simple flattened rings."""

    result, _ = _resolve_filled_faces(rings, allow_self_intersections=False)
    return result


def _self_intersection_details(rings: Sequence[Sequence[XY]]):
    self_intersecting = []
    crossing_count = 0
    point_crossings_only = True
    for ring_index, ring in enumerate(rings):
        closed = list(ring) + [ring[0]]
        line = LineString(closed)
        if line.is_simple:
            continue
        self_intersecting.append(ring_index)
        edges = [LineString((closed[index], closed[index + 1])) for index in range(len(ring))]
        for first_index, first in enumerate(edges):
            for second_index in range(first_index + 1, len(edges)):
                if second_index == first_index + 1:
                    continue
                if first_index == 0 and second_index == len(edges) - 1:
                    continue
                intersection = first.intersection(edges[second_index])
                if intersection.is_empty:
                    continue
                if intersection.geom_type == "Point":
                    crossing_count += 1
                elif intersection.geom_type == "MultiPoint":
                    crossing_count += len(intersection.geoms)
                else:
                    point_crossings_only = False
    return tuple(self_intersecting), crossing_count, point_crossings_only


def normalize_outline(outline: GlyphOutline, tolerance: float):
    """Flatten and resolve a visible non-zero fill with bounded overlap handling."""

    rings = flatten_outline(outline, tolerance)
    self_intersecting, crossing_count, point_crossings_only = _self_intersection_details(rings)
    if not self_intersecting:
        silhouette, details = _resolve_filled_faces(rings, allow_self_intersections=False)
        diagnostics = NormalizationDiagnostics(
            fill_rule="non-zero winding",
            normalization_applied=False,
            cause="simple source contours",
            self_intersecting_contours=(),
            point_crossing_count=0,
            primary_face_count=details["face_count"],
            reference_face_count=details["face_count"],
            winding_histogram=details["winds"],
            maximum_absolute_winding=max(abs(value) for value in details["winds"]),
            nonzero_area=silhouette.area,
            evenodd_area=details["evenodd_area"],
            cross_tolerance_symmetric_difference=0.0,
            cross_tolerance_normalized_difference=0.0,
            cross_tolerance_hausdorff_distance=0.0,
        )
        return rings, silhouette, diagnostics

    if not point_crossings_only:
        raise UnsupportedOutlineError(
            "self-intersection contains coincident or overlapping edge geometry; bounded overlap normalization refused"
        )

    silhouette, primary = _resolve_filled_faces(rings, allow_self_intersections=True)
    reference_rings = flatten_outline(outline, tolerance / 2.0)
    reference_self_intersecting, _, reference_points_only = _self_intersection_details(reference_rings)
    reference, reference_details = _resolve_filled_faces(
        reference_rings, allow_self_intersections=True
    )
    maximum_winding = max(abs(value) for value in primary["winds"])
    symmetric_difference = silhouette.symmetric_difference(reference).area
    normalized_difference = symmetric_difference / reference.area
    hausdorff = silhouette.boundary.hausdorff_distance(reference.boundary)
    topology_stable = (
        self_intersecting == reference_self_intersecting
        and primary["face_count"] == reference_details["face_count"]
        and primary["selected_count"] == reference_details["selected_count"]
        and primary["winds"] == reference_details["winds"]
    )
    geometry_stable = (
        normalized_difference <= MAX_CROSS_TOLERANCE_NORMALIZED_DIFFERENCE
        and hausdorff <= tolerance
    )
    if (
        maximum_winding < 2
        or not reference_points_only
        or not topology_stable
        or not geometry_stable
    ):
        reasons = []
        if maximum_winding < 2:
            reasons.append("no multiply-wound overlap region")
        if not reference_points_only:
            reasons.append("reference contains non-point intersections")
        if not topology_stable:
            reasons.append("intersection topology changes with flattening tolerance")
        if not geometry_stable:
            reasons.append("resolved silhouette is unstable across flattening tolerances")
        raise UnsupportedOutlineError(
            "self-intersection is not a stable intentional overlap; bounded normalization refused: "
            + "; ".join(reasons)
        )

    diagnostics = NormalizationDiagnostics(
        fill_rule="non-zero winding",
        normalization_applied=True,
        cause="stable multiply-wound overlapping source construction",
        self_intersecting_contours=self_intersecting,
        point_crossing_count=crossing_count,
        primary_face_count=primary["face_count"],
        reference_face_count=reference_details["face_count"],
        winding_histogram=primary["winds"],
        maximum_absolute_winding=maximum_winding,
        nonzero_area=silhouette.area,
        evenodd_area=primary["evenodd_area"],
        cross_tolerance_symmetric_difference=symmetric_difference,
        cross_tolerance_normalized_difference=normalized_difference,
        cross_tolerance_hausdorff_distance=hausdorff,
    )
    return rings, silhouette, diagnostics


def geometry_polygons(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return [part for part in getattr(geometry, "geoms", ()) if isinstance(part, Polygon)]


def canonical_ring(points: Iterable[XY], *, clockwise: bool) -> tuple[XY, ...]:
    ring = tuple((float(x), float(y)) for x, y in points)
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise UnsupportedOutlineError("clipping produced a contour with fewer than three points")
    is_clockwise = signed_area(ring) < 0
    if is_clockwise != clockwise:
        ring = tuple(reversed(ring))
    start = min(range(len(ring)), key=lambda index: (round(ring[index][0], 9), round(ring[index][1], 9)))
    return ring[start:] + ring[:start]


def geometry_to_canonical_rings(geometry) -> tuple[tuple[bool, tuple[XY, ...]], ...]:
    polygons = geometry_polygons(geometry)
    polygons.sort(
        key=lambda polygon: (
            round(polygon.bounds[0], 9),
            round(polygon.bounds[1], 9),
            -round(polygon.area, 9),
            polygon.normalize().wkb_hex,
        )
    )
    result: list[tuple[bool, tuple[XY, ...]]] = []
    for polygon in polygons:
        result.append((False, canonical_ring(polygon.exterior.coords, clockwise=False)))
        holes = [canonical_ring(interior.coords, clockwise=True) for interior in polygon.interiors]
        holes.sort(key=lambda ring: (round(min(x for x, _ in ring), 9), round(min(y for _, y in ring), 9)))
        result.extend((True, ring) for ring in holes)
    return tuple(result)


def master_contours_to_union(contours: Sequence[MasterContour]):
    return visible_filled_union([contour.points for contour in contours])


def interpolate_contours(
    intact: Sequence[MasterContour], eroded: Sequence[MasterContour], factor: float
) -> tuple[MasterContour, ...]:
    result = []
    for first, second in zip(intact, eroded, strict=True):
        points = tuple(
            (
                a[0] + (b[0] - a[0]) * factor,
                a[1] + (b[1] - a[1]) * factor,
            )
            for a, b in zip(first.points, second.points, strict=True)
        )
        result.append(
            MasterContour(
                identifier=first.identifier,
                fragment_id=first.fragment_id,
                part_index=first.part_index,
                is_hole=first.is_hole,
                points=points,
                point_ids=first.point_ids,
            )
        )
    return tuple(result)
