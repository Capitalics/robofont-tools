from __future__ import annotations

"""One-glyph hybrid cubic/line reconstruction proof.

This module is development-only. It consumes existing canonical macro faces but
does not participate in production generation or serialization.
"""

from dataclasses import dataclass
import hashlib
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge, unary_union

from fracturize.model import CubicSegment, GlyphOutline, LineSegment, Point as XY
from test_support.cubic_intersections import (
    cubic_point,
    intersect_cubic_with_line,
    split_cubic_many,
)


@dataclass(frozen=True)
class HybridSegment:
    identifier: str
    kind: str  # "exterior" or "internal"
    geometry: CubicSegment | LineSegment
    source_contour_index: int | None = None
    source_segment_index: int | None = None
    source_t_range: tuple[float, float] | None = None


@dataclass(frozen=True)
class HybridContour:
    identifier: str
    segments: tuple[HybridSegment, ...]


@dataclass(frozen=True)
class HybridFragment:
    identifier: str
    face_index: int
    contours: tuple[HybridContour, ...]
    transform_origin: XY
    translation: XY
    rotation_degrees: float
    scale: float


@dataclass(frozen=True)
class HybridGlyph:
    name: str
    width: float
    fragments: tuple[HybridFragment, ...]


@dataclass(frozen=True)
class HybridProof:
    intact: HybridGlyph
    eroded: HybridGlyph
    faces: tuple[Polygon, ...]
    crack_lines: tuple[LineString, ...]
    new_exterior_nodes: tuple[XY, ...]
    shared_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class _BoundaryEdge:
    identifier: str
    kind: str
    faces: tuple[int, ...]
    segments: tuple[HybridSegment, ...]

    @property
    def start(self):
        return self.segments[0].geometry.start

    @property
    def end(self):
        return self.segments[-1].geometry.end


def _coordinate_key(point: XY, precision=1e-6):
    return (round(point[0] / precision), round(point[1] / precision))


def _line_geometries(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type in {"LineString", "LinearRing"}:
        return [LineString(geometry.coords)]
    if hasattr(geometry, "geoms"):
        result = []
        for item in geometry.geoms:
            result.extend(_line_geometries(item))
        return result
    return []


def _shared_face_paths(faces, minimum_length):
    records = []
    for first in range(len(faces)):
        for second in range(first):
            shared = faces[first].boundary.intersection(faces[second].boundary)
            lines = [line for line in _line_geometries(shared) if line.length > minimum_length]
            if not lines:
                continue
            merged_union = unary_union(lines)
            merged = (
                merged_union
                if merged_union.geom_type == "LineString"
                else linemerge(merged_union)
            )
            for line in _line_geometries(merged):
                if line.length > minimum_length:
                    records.append(((second, first), line))
    return records


def _crack_segments(crack_lines):
    for crack in crack_lines:
        coordinates = list(crack.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            if start != end:
                yield LineSegment(tuple(start), tuple(end))


def _exact_boundary_intersections(
    outline: GlyphOutline,
    crack_lines,
    proxy_boundary_endpoints,
    match_tolerance,
):
    candidates = []
    for contour_index, contour in enumerate(outline.contours):
        for segment_index, source_segment in enumerate(contour.segments):
            if not isinstance(source_segment, CubicSegment):
                continue
            for crack_segment in _crack_segments(crack_lines):
                for intersection in intersect_cubic_with_line(
                    source_segment,
                    crack_segment,
                    proxy_tolerance=max(match_tolerance * 0.25, 0.01),
                    refinement_tolerance=1e-10,
                ):
                    if any(
                        math.dist(intersection.point, endpoint) <= match_tolerance
                        for endpoint in proxy_boundary_endpoints
                    ):
                        candidates.append(
                            (
                                contour_index,
                                segment_index,
                                intersection.t,
                                intersection.point,
                            )
                        )
    unique = []
    for candidate in sorted(candidates, key=lambda item: (item[0], item[1], item[2])):
        if unique and (
            candidate[:2] == unique[-1][:2]
            and abs(candidate[2] - unique[-1][2]) <= 1e-9
        ):
            continue
        unique.append(candidate)
    return tuple(unique)


def _snap_shared_paths(shared_paths, exact_intersections, match_tolerance):
    exact_points = [record[3] for record in exact_intersections]
    snapped = []
    for faces, line in shared_paths:
        coordinates = [tuple(point) for point in line.coords]
        for index in (0, len(coordinates) - 1):
            if not exact_points:
                continue
            nearest = min(exact_points, key=lambda point: math.dist(coordinates[index], point))
            if math.dist(coordinates[index], nearest) <= match_tolerance:
                coordinates[index] = nearest
        # Canonical storage direction makes reuse auditable. Each face later
        # chooses this sequence or its exact reverse.
        if coordinates[-1] < coordinates[0]:
            coordinates.reverse()
        snapped.append((faces, tuple(coordinates)))
    return tuple(snapped)


def _canonicalize_split_nodes(outline, exact_intersections):
    """Use the actual de Casteljau piece endpoints as shared graph nodes."""

    grouped = {}
    for record in exact_intersections:
        grouped.setdefault(record[:2], []).append(record)
    canonical = []
    for (contour_index, segment_index), records in sorted(grouped.items()):
        records = sorted(records, key=lambda item: item[2])
        source = outline.contours[contour_index].segments[segment_index]
        pieces = split_cubic_many(source, [record[2] for record in records])
        for index, record in enumerate(records):
            canonical.append((*record[:3], pieces[index].end))
    return tuple(sorted(canonical, key=lambda item: (item[0], item[1], item[2])))


def _shared_edges(snapped_paths):
    edges = []
    for index, (faces, coordinates) in enumerate(snapped_paths):
        digest = hashlib.sha256(repr((faces, coordinates)).encode("utf-8")).hexdigest()[:16]
        edge_id = f"shared-{digest}"
        segments = tuple(
            HybridSegment(
                identifier=f"{edge_id}-s{segment_index}",
                kind="internal",
                geometry=LineSegment(start, end),
            )
            for segment_index, (start, end) in enumerate(
                zip(coordinates, coordinates[1:])
            )
            if start != end
        )
        if segments:
            edges.append(_BoundaryEdge(edge_id, "internal", faces, segments))
    return tuple(edges)


def _exterior_edges(outline, exact_intersections, faces, assignment_tolerance):
    by_source_segment = {}
    for contour_index, segment_index, parameter, _ in exact_intersections:
        by_source_segment.setdefault((contour_index, segment_index), []).append(parameter)

    edges = []
    for contour_index, contour in enumerate(outline.contours):
        for segment_index, source_segment in enumerate(contour.segments):
            parameters = sorted(by_source_segment.get((contour_index, segment_index), ()))
            if isinstance(source_segment, CubicSegment):
                pieces = split_cubic_many(source_segment, parameters)
            else:
                if parameters:
                    raise ValueError("Phase 2 proof does not split source line segments")
                pieces = (source_segment,)
            boundaries = (0.0, *parameters, 1.0)
            for piece_index, (piece, start_t, end_t) in enumerate(
                zip(pieces, boundaries, boundaries[1:])
            ):
                midpoint = (
                    cubic_point(piece, 0.5)
                    if isinstance(piece, CubicSegment)
                    else (
                        (piece.start[0] + piece.end[0]) * 0.5,
                        (piece.start[1] + piece.end[1]) * 0.5,
                    )
                )
                distances = [face.boundary.distance(Point(midpoint)) for face in faces]
                face_index = min(range(len(faces)), key=distances.__getitem__)
                if distances[face_index] > assignment_tolerance:
                    raise ValueError(
                        "cannot map an exact source-curve interval to a macro face"
                    )
                edge_id = f"exterior-c{contour_index}-s{segment_index}-p{piece_index}"
                segment = HybridSegment(
                    identifier=edge_id,
                    kind="exterior",
                    geometry=piece,
                    source_contour_index=contour_index,
                    source_segment_index=segment_index,
                    source_t_range=(start_t, end_t),
                )
                edges.append(
                    _BoundaryEdge(edge_id, "exterior", (face_index,), (segment,))
                )
    return tuple(edges)


def _reverse_segment(segment):
    geometry = segment.geometry
    if isinstance(geometry, CubicSegment):
        reversed_geometry = CubicSegment(
            geometry.end,
            geometry.control2,
            geometry.control1,
            geometry.start,
        )
        source_range = (
            tuple(reversed(segment.source_t_range))
            if segment.source_t_range is not None
            else None
        )
    else:
        reversed_geometry = LineSegment(geometry.end, geometry.start)
        source_range = segment.source_t_range
    return HybridSegment(
        identifier=segment.identifier,
        kind=segment.kind,
        geometry=reversed_geometry,
        source_contour_index=segment.source_contour_index,
        source_segment_index=segment.source_segment_index,
        source_t_range=source_range,
    )


def _oriented_edge(edge, start_key):
    if _coordinate_key(edge.start) == start_key:
        return edge.segments
    if _coordinate_key(edge.end) == start_key:
        if edge.kind == "exterior":
            raise ValueError("face assembly would reverse original contour direction")
        return tuple(_reverse_segment(segment) for segment in reversed(edge.segments))
    raise ValueError("edge does not meet requested boundary node")


def _signed_area_for_segments(segments):
    points = []
    for segment in segments:
        geometry = segment.geometry
        if isinstance(geometry, CubicSegment):
            points.extend(cubic_point(geometry, index / 16) for index in range(16))
        else:
            points.append(geometry.start)
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:] + points[:1])
    )


def _assemble_face_contours(face_index, face_edges, fragment_id):
    unused = list(face_edges)
    contours = []
    while unused:
        exterior_seed = next((edge for edge in unused if edge.kind == "exterior"), None)
        seed = exterior_seed or unused[0]
        start_key = _coordinate_key(seed.start)
        oriented = seed.segments
        unused.remove(seed)
        assembled = list(oriented)
        current_key = _coordinate_key(assembled[-1].geometry.end)
        while current_key != start_key:
            candidates = [
                edge
                for edge in unused
                if current_key in {_coordinate_key(edge.start), _coordinate_key(edge.end)}
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"face {face_index} boundary is ambiguous at {current_key}: "
                    f"{len(candidates)} candidate edges"
                )
            edge = candidates[0]
            oriented = _oriented_edge(edge, current_key)
            assembled.extend(oriented)
            unused.remove(edge)
            current_key = _coordinate_key(assembled[-1].geometry.end)
        if not exterior_seed and _signed_area_for_segments(assembled) < 0:
            assembled = [
                _reverse_segment(segment) for segment in reversed(assembled)
            ]
        contours.append(
            HybridContour(
                identifier=f"{fragment_id}-c{len(contours)}",
                segments=tuple(assembled),
            )
        )
    return tuple(contours)


def _transform_point(point, origin, translation, rotation_degrees, scale):
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    local_x = (point[0] - origin[0]) * scale
    local_y = (point[1] - origin[1]) * scale
    return (
        origin[0] + local_x * cosine - local_y * sine + translation[0],
        origin[1] + local_x * sine + local_y * cosine + translation[1],
    )


def _transform_segment(segment, origin, translation, rotation, scale):
    geometry = segment.geometry
    if isinstance(geometry, CubicSegment):
        moved = CubicSegment(
            *(
                _transform_point(point, origin, translation, rotation, scale)
                for point in (
                    geometry.start,
                    geometry.control1,
                    geometry.control2,
                    geometry.end,
                )
            )
        )
    else:
        moved = LineSegment(
            _transform_point(geometry.start, origin, translation, rotation, scale),
            _transform_point(geometry.end, origin, translation, rotation, scale),
        )
    return HybridSegment(
        identifier=segment.identifier,
        kind=segment.kind,
        geometry=moved,
        source_contour_index=segment.source_contour_index,
        source_segment_index=segment.source_segment_index,
        source_t_range=segment.source_t_range,
    )


def _eroded_fragment(fragment):
    contours = tuple(
        HybridContour(
            contour.identifier,
            tuple(
                _transform_segment(
                    segment,
                    fragment.transform_origin,
                    fragment.translation,
                    fragment.rotation_degrees,
                    fragment.scale,
                )
                for segment in contour.segments
            ),
        )
        for contour in fragment.contours
    )
    return HybridFragment(
        identifier=fragment.identifier,
        face_index=fragment.face_index,
        contours=contours,
        transform_origin=fragment.transform_origin,
        translation=fragment.translation,
        rotation_degrees=fragment.rotation_degrees,
        scale=fragment.scale,
    )


def reconstruct_hybrid_glyph(
    outline,
    faces,
    crack_lines,
    guide_fragments,
    *,
    flattening_tolerance,
):
    """Reconstruct one contour-only glyph from exact exterior and line cuts."""

    if outline.components:
        raise ValueError("Phase 2 hybrid proof does not support components")
    if len(faces) != len(guide_fragments):
        raise ValueError("macro faces and motion guide fragments differ")
    minimum_length = max(outline.units_per_em * 1e-9, 1e-7)
    shared_paths = _shared_face_paths(faces, minimum_length)
    proxy_endpoints = []
    for _, line in shared_paths:
        for endpoint in (tuple(line.coords[0]), tuple(line.coords[-1])):
            # Only endpoints on a source boundary require curve refinement.
            proxy_endpoints.append(endpoint)
    match_tolerance = max(flattening_tolerance * 3.0, 0.05)
    exact_intersections = _exact_boundary_intersections(
        outline,
        crack_lines,
        proxy_endpoints,
        match_tolerance,
    )
    exact_intersections = _canonicalize_split_nodes(outline, exact_intersections)
    snapped_paths = _snap_shared_paths(
        shared_paths,
        exact_intersections,
        match_tolerance,
    )
    internal_edges = _shared_edges(snapped_paths)
    exterior_edges = _exterior_edges(
        outline,
        exact_intersections,
        faces,
        assignment_tolerance=max(flattening_tolerance * 2.0, 0.1),
    )

    intact_fragments = []
    for face_index, guide in enumerate(guide_fragments):
        edges = [
            edge
            for edge in (*exterior_edges, *internal_edges)
            if face_index in edge.faces
        ]
        contours = _assemble_face_contours(face_index, edges, guide.identifier)
        intact_fragments.append(
            HybridFragment(
                identifier=guide.identifier,
                face_index=face_index,
                contours=contours,
                transform_origin=guide.transform_origin,
                translation=guide.translation,
                rotation_degrees=guide.rotation_degrees,
                scale=guide.scale,
            )
        )
    intact = HybridGlyph(outline.name, outline.width, tuple(intact_fragments))
    eroded = HybridGlyph(
        outline.name,
        outline.width,
        tuple(_eroded_fragment(fragment) for fragment in intact_fragments),
    )
    new_nodes = tuple(
        sorted({tuple(record[3]) for record in exact_intersections})
    )
    return HybridProof(
        intact=intact,
        eroded=eroded,
        faces=tuple(faces),
        crack_lines=tuple(crack_lines),
        new_exterior_nodes=new_nodes,
        shared_edge_ids=tuple(edge.identifier for edge in internal_edges),
    )


def structural_signature(glyph):
    return tuple(
        (
            fragment.identifier,
            tuple(
                (
                    contour.identifier,
                    tuple(
                        (
                            segment.identifier,
                            segment.kind,
                            type(segment.geometry).__name__,
                        )
                        for segment in contour.segments
                    ),
                )
                for contour in fragment.contours
            ),
        )
        for fragment in glyph.fragments
    )


def shared_internal_edge_uses(glyph):
    uses = {}
    for fragment in glyph.fragments:
        for contour in fragment.contours:
            for segment in contour.segments:
                if segment.kind == "internal":
                    uses.setdefault(segment.identifier, []).append(
                        (fragment.identifier, segment.geometry)
                    )
    return uses


def _interpolate_point(first, second, factor):
    return (
        first[0] + (second[0] - first[0]) * factor,
        first[1] + (second[1] - first[1]) * factor,
    )


def interpolate_hybrid_glyph(intact, eroded, factor):
    if structural_signature(intact) != structural_signature(eroded):
        raise ValueError("hybrid masters are not structurally compatible")
    fragments = []
    for first_fragment, second_fragment in zip(
        intact.fragments, eroded.fragments, strict=True
    ):
        contours = []
        for first_contour, second_contour in zip(
            first_fragment.contours, second_fragment.contours, strict=True
        ):
            segments = []
            for first, second in zip(
                first_contour.segments, second_contour.segments, strict=True
            ):
                if isinstance(first.geometry, CubicSegment):
                    geometry = CubicSegment(
                        *(
                            _interpolate_point(a, b, factor)
                            for a, b in zip(
                                (
                                    first.geometry.start,
                                    first.geometry.control1,
                                    first.geometry.control2,
                                    first.geometry.end,
                                ),
                                (
                                    second.geometry.start,
                                    second.geometry.control1,
                                    second.geometry.control2,
                                    second.geometry.end,
                                ),
                                strict=True,
                            )
                        )
                    )
                else:
                    geometry = LineSegment(
                        _interpolate_point(
                            first.geometry.start, second.geometry.start, factor
                        ),
                        _interpolate_point(
                            first.geometry.end, second.geometry.end, factor
                        ),
                    )
                segments.append(
                    HybridSegment(
                        identifier=first.identifier,
                        kind=first.kind,
                        geometry=geometry,
                        source_contour_index=first.source_contour_index,
                        source_segment_index=first.source_segment_index,
                        source_t_range=first.source_t_range,
                    )
                )
            contours.append(HybridContour(first_contour.identifier, tuple(segments)))
        fragments.append(
            HybridFragment(
                identifier=first_fragment.identifier,
                face_index=first_fragment.face_index,
                contours=tuple(contours),
                transform_origin=first_fragment.transform_origin,
                translation=first_fragment.translation,
                rotation_degrees=first_fragment.rotation_degrees,
                scale=first_fragment.scale,
            )
        )
    return HybridGlyph(intact.name, intact.width, tuple(fragments))


def sample_hybrid_contour(contour, samples_per_cubic=256):
    points = []
    for segment in contour.segments:
        geometry = segment.geometry
        if isinstance(geometry, CubicSegment):
            points.extend(
                cubic_point(geometry, index / samples_per_cubic)
                for index in range(samples_per_cubic)
            )
        else:
            points.append(geometry.start)
    points.append(contour.segments[-1].geometry.end)
    return tuple(points)


def hybrid_glyph_geometry(glyph, samples_per_cubic=256):
    polygons = []
    for fragment in glyph.fragments:
        for contour in fragment.contours:
            polygon = Polygon(sample_hybrid_contour(contour, samples_per_cubic))
            if not polygon.is_valid or polygon.area <= 0:
                raise ValueError(f"invalid hybrid contour: {contour.identifier}")
            polygons.append(polygon)
    return unary_union(polygons)
