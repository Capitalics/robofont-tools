from __future__ import annotations

"""Hybrid fragment contours with exact source exteriors and line-only cuts."""

from dataclasses import dataclass
import hashlib
import math

from shapely.geometry import LineString, Point
from shapely.ops import linemerge, substring, unary_union

from .cubic import (
    cubic_point,
    intersect_cubic_with_line,
    intersect_line_with_line,
    split_cubic_many,
    split_line_many,
)
from .geometry import UnsupportedOutlineError, signed_area
from .model import CubicSegment, GlyphOutline, LineSegment, MasterContour, Segment


@dataclass(frozen=True)
class _TaggedSegment:
    identifier: str
    geometry: Segment
    exterior: bool


@dataclass(frozen=True)
class _Edge:
    identifier: str
    faces: tuple[int, ...]
    segments: tuple[_TaggedSegment, ...]
    exterior: bool

    @property
    def start(self):
        return self.segments[0].geometry.start

    @property
    def end(self):
        return self.segments[-1].geometry.end


def _key(point, precision=1e-5):
    return round(point[0] / precision), round(point[1] / precision)


def _matches(first, second, tolerance=1e-4):
    return math.dist(first, second) <= tolerance


def _lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type in {"LineString", "LinearRing"}:
        return [LineString(geometry.coords)]
    result = []
    for item in getattr(geometry, "geoms", ()):
        result.extend(_lines(item))
    return result


def _shared_paths(faces, minimum_length):
    records = []
    for first in range(len(faces)):
        for second in range(first):
            shared = faces[first].boundary.intersection(faces[second].boundary)
            lines = [line for line in _lines(shared) if line.length > minimum_length]
            if not lines:
                continue
            merged_union = unary_union(lines)
            merged = merged_union if merged_union.geom_type == "LineString" else linemerge(merged_union)
            for line in _lines(merged):
                if line.length > minimum_length:
                    records.append(((second, first), line))
    endpoints = [Point(coordinate) for _, line in records for coordinate in line.coords]
    noded = []
    for faces_pair, line in records:
        distances = {0.0, line.length}
        for endpoint in endpoints:
            distance = line.project(endpoint)
            if minimum_length < distance < line.length - minimum_length:
                projected = line.interpolate(distance)
                if projected.distance(endpoint) <= max(minimum_length * 10, 1e-6):
                    distances.add(distance)
        ordered = sorted(distances)
        for start, end in zip(ordered, ordered[1:]):
            piece = substring(line, start, end)
            if piece.length > minimum_length:
                noded.append((faces_pair, LineString(piece.coords)))
    return noded


def _crack_segments(crack_lines):
    for crack in crack_lines:
        coordinates = list(crack.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            if start != end:
                yield LineSegment(tuple(start), tuple(end))


def _exact_intersections(outline, crack_lines, boundary_endpoints, tolerance):
    candidates = []
    cutters = []
    extension = tolerance * 6.0
    for crack in crack_lines:
        coordinates = [tuple(point) for point in crack.coords]
        for index, (start, end) in enumerate(zip(coordinates, coordinates[1:])):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            # Polygonization can place a crack vertex just inside the flattened
            # proxy boundary. Extend only local endpoints which actually touch
            # that proxy; extending every section creates false curve hits.
            if any(math.dist(start, point) <= tolerance * 2 for point in boundary_endpoints):
                start = (start[0] - dx / length * extension, start[1] - dy / length * extension)
            if any(math.dist(end, point) <= tolerance * 2 for point in boundary_endpoints):
                end = (end[0] + dx / length * extension, end[1] + dy / length * extension)
            cutters.append(LineSegment(start, end))
    for contour_index, contour in enumerate(outline.contours):
        for segment_index, source in enumerate(contour.segments):
            for cutter in cutters:
                if isinstance(source, CubicSegment):
                    intersections = intersect_cubic_with_line(
                        source,
                        cutter,
                        proxy_tolerance=max(tolerance * 0.2, 0.01),
                    )
                else:
                    intersections = intersect_line_with_line(source, cutter)
                for intersection in intersections:
                    if intersection.tangent:
                        raise UnsupportedOutlineError(
                            f"ambiguous tangential fracture intersection at contour {contour_index}, segment {segment_index}"
                        )
                    if intersection.t <= 1e-8 or intersection.t >= 1 - 1e-8:
                        # Existing source nodes need no subdivision. They are
                        # retained, but endpoint coincidences must be unique.
                        continue
                    endpoint_distance = min(
                        (math.dist(intersection.point, endpoint) for endpoint in boundary_endpoints),
                        default=math.inf,
                    )
                    if endpoint_distance <= tolerance:
                        candidates.append(
                            (contour_index, segment_index, intersection.t, intersection.point, endpoint_distance)
                        )
    unique = []
    for candidate in sorted(candidates, key=lambda item: (item[0], item[1], item[2])):
        if unique and candidate[:2] == unique[-1][:2] and math.dist(candidate[3], unique[-1][3]) <= tolerance:
            if candidate[4] < unique[-1][4]:
                unique[-1] = candidate
            continue
        unique.append(candidate)
    return tuple(candidate[:4] for candidate in unique)


def _canonical_split_nodes(outline, intersections):
    grouped = {}
    for record in intersections:
        grouped.setdefault(record[:2], []).append(record)
    result = []
    for (contour_index, segment_index), records in sorted(grouped.items()):
        records.sort(key=lambda item: item[2])
        source = outline.contours[contour_index].segments[segment_index]
        parameters = [record[2] for record in records]
        pieces = (
            split_cubic_many(source, parameters)
            if isinstance(source, CubicSegment)
            else split_line_many(source, parameters)
        )
        for index, record in enumerate(records):
            result.append((*record[:3], pieces[index].end))
    return tuple(result)


def _snap_shared_paths(shared_paths, exact_intersections, tolerance):
    exact_points = [record[3] for record in exact_intersections]
    snapped = []
    for faces, line in shared_paths:
        coordinates = [tuple(point) for point in line.coords]
        for index in (0, -1):
            if exact_points:
                nearest = min(exact_points, key=lambda point: math.dist(coordinates[index], point))
                if math.dist(coordinates[index], nearest) <= tolerance:
                    coordinates[index] = nearest
        if coordinates[-1] < coordinates[0]:
            coordinates.reverse()
        snapped.append((faces, tuple(coordinates)))
    return tuple(snapped)


def _internal_edges(paths):
    edges = []
    for faces, coordinates in paths:
        payload = repr((faces, coordinates)).encode("utf-8")
        identifier = "cut-" + hashlib.sha256(payload).hexdigest()[:16]
        segments = tuple(
            _TaggedSegment(f"{identifier}-s{index}", LineSegment(start, end), False)
            for index, (start, end) in enumerate(zip(coordinates, coordinates[1:]))
            if start != end
        )
        if segments:
            edges.append(_Edge(identifier, faces, segments, False))
    return tuple(edges)


def _face_internal_edges(faces, silhouette, exact_intersections, boundary_tolerance):
    exact_points = [record[3] for record in exact_intersections]
    edges_by_face = [[] for _ in faces]
    for face_index, face in enumerate(faces):
        for ring in (face.exterior, *face.interiors):
            coordinates = [tuple(point) for point in ring.coords]
            for index in range(len(coordinates) - 1):
                start, end = coordinates[index], coordinates[index + 1]
                candidate_line = LineString((start, end))
                boundary_overlap = candidate_line.intersection(silhouette.boundary).length
                if boundary_overlap >= candidate_line.length * 0.9:
                    continue
                snapped = []
                for point in (start, end):
                    if exact_points:
                        nearest = min(exact_points, key=lambda item: math.dist(point, item))
                        if math.dist(point, nearest) <= boundary_tolerance * 3:
                            point = nearest
                    snapped.append(point)
                start, end = snapped
                if math.dist(start, end) <= 1e-7:
                    continue
                canonical = tuple(sorted((_key(start), _key(end))))
                identifier = "cut-" + hashlib.sha256(repr(canonical).encode("ascii")).hexdigest()[:16]
                edges_by_face[face_index].append(
                    _Edge(
                        identifier,
                        (face_index,),
                        (_TaggedSegment(identifier, LineSegment(start, end), False),),
                        False,
                    )
                )
    return tuple(tuple(edges) for edges in edges_by_face)


def _segment_midpoint(segment):
    if isinstance(segment, CubicSegment):
        return cubic_point(segment, 0.5)
    return ((segment.start[0] + segment.end[0]) * 0.5, (segment.start[1] + segment.end[1]) * 0.5)


def _segment_midpoint_direction(segment):
    if isinstance(segment, CubicSegment):
        from .cubic import cubic_derivative

        return cubic_derivative(segment, 0.5)
    return segment.end[0] - segment.start[0], segment.end[1] - segment.start[1]


def _exterior_edges(outline, intersections, faces, assignment_tolerance):
    grouped = {}
    for contour_index, segment_index, parameter, _ in intersections:
        grouped.setdefault((contour_index, segment_index), []).append(parameter)
    edges = []
    for contour_index, contour in enumerate(outline.contours):
        for segment_index, source in enumerate(contour.segments):
            parameters = sorted(grouped.get((contour_index, segment_index), ()))
            pieces = (
                split_cubic_many(source, parameters)
                if isinstance(source, CubicSegment)
                else split_line_many(source, parameters)
            )
            for piece_index, piece in enumerate(pieces):
                midpoint = Point(_segment_midpoint(piece))
                direction = _segment_midpoint_direction(piece)
                length = math.hypot(*direction)
                probe_distance = max(assignment_tolerance * 0.2, 0.05)
                probes = []
                if length > 1e-10:
                    normal = (-direction[1] / length, direction[0] / length)
                    probes = [
                        Point(midpoint.x + sign * normal[0] * probe_distance,
                              midpoint.y + sign * normal[1] * probe_distance)
                        for sign in (1.0, -1.0)
                    ]
                containing = [
                    index
                    for index, face in enumerate(faces)
                    if any(face.buffer(1e-7).contains(probe) for probe in probes)
                ]
                distances = [face.boundary.distance(midpoint) for face in faces]
                face_index = (
                    min(containing, key=distances.__getitem__)
                    if containing
                    else min(range(len(faces)), key=distances.__getitem__)
                )
                if distances[face_index] > assignment_tolerance:
                    raise UnsupportedOutlineError(
                        f"ambiguous exterior interval at contour {contour_index}, segment {segment_index}"
                    )
                identifier = f"source-c{contour_index}-s{segment_index}-p{piece_index}"
                edges.append(
                    _Edge(
                        identifier,
                        (face_index,),
                        (_TaggedSegment(identifier, piece, True),),
                        True,
                    )
                )
    return tuple(edges)


def _reverse(tagged):
    segment = tagged.geometry
    if isinstance(segment, CubicSegment):
        segment = CubicSegment(segment.end, segment.control2, segment.control1, segment.start)
    else:
        segment = LineSegment(segment.end, segment.start)
    return _TaggedSegment(tagged.identifier, segment, tagged.exterior)


def _orient(edge, start):
    if _matches(edge.start, start):
        return edge.segments
    if _matches(edge.end, start):
        if edge.exterior:
            raise UnsupportedOutlineError("hybrid face assembly would reverse source contour direction")
        return tuple(_reverse(segment) for segment in reversed(edge.segments))
    raise UnsupportedOutlineError("hybrid edge does not meet the requested node")


def _segment_samples(segments):
    points = []
    for tagged in segments:
        segment = tagged.geometry
        if isinstance(segment, CubicSegment):
            points.extend(cubic_point(segment, index / 12) for index in range(12))
        else:
            points.append(segment.start)
    return points


def _assemble(face_index, face, edges, fragment_id):
    unused = list(edges)
    contours = []
    while unused:
        seed = next((edge for edge in unused if edge.exterior), unused[0])
        start = seed.start
        available = [edge for edge in unused if edge is not seed]

        def complete(path, assembled, current, remaining):
            if _matches(current, start):
                return path, assembled
            candidates = sorted(
                (
                    edge for edge in remaining
                    if _matches(current, edge.start) or _matches(current, edge.end)
                ),
                key=lambda edge: (not edge.exterior, edge.identifier),
            )
            for edge in candidates:
                try:
                    oriented = _orient(edge, current)
                except UnsupportedOutlineError:
                    continue
                result = complete(
                    path + [edge],
                    assembled + list(oriented),
                    oriented[-1].geometry.end,
                    [candidate for candidate in remaining if candidate is not edge],
                )
                if result is not None:
                    return result
            return None

        completed = complete(
            [seed],
            list(seed.segments),
            seed.end,
            available,
        )
        if completed is None:
            raise UnsupportedOutlineError(
                f"ambiguous hybrid boundary for face {face_index}: no closed edge cycle"
            )
        used, assembled = completed
        unused = [edge for edge in unused if edge not in used]
        if not any(segment.exterior for segment in assembled):
            samples = _segment_samples(assembled)
            if signed_area(samples) < 0:
                assembled = [_reverse(segment) for segment in reversed(assembled)]
        segments = tuple(segment.geometry for segment in assembled)
        if len(segments) < 3:
            # A two-edge cycle can only be a proxy/refinement sliver at a
            # crack/curve intersection; it is not a valid UFO contour.
            continue
        contour_index = len(contours)
        contour_id = f"{fragment_id}-c{contour_index}"
        points = tuple(segment.end for segment in segments)
        point_ids = tuple(
            f"{contour_id}-p{index}-{assembled[index].identifier}"
            for index in range(len(segments))
        )
        contours.append(
            MasterContour(
                contour_id,
                fragment_id,
                contour_index,
                signed_area(_segment_samples(assembled)) < 0,
                points,
                point_ids,
                segments,
            )
        )
    return tuple(contours)


def reconstruct_hybrid_contours(
    outline: GlyphOutline,
    faces,
    crack_lines,
    fragment_ids,
    *,
    flattening_tolerance: float,
):
    """Return exact-exterior contours in the same order as canonical faces."""

    if outline.components:
        raise UnsupportedOutlineError("components are unsupported by hybrid reconstruction")
    if len(faces) != len(fragment_ids):
        raise UnsupportedOutlineError("canonical and profiled fragment counts differ")
    # GEOS can emit microscopic shared-boundary spurs where several profiled
    # cracks meet. They are clipping artifacts, not fracture edges.
    minimum_length = max(
        outline.units_per_em * 1e-4,
        flattening_tolerance * 0.2,
        1e-7,
    )
    silhouette = unary_union(faces)
    boundary_endpoints = tuple(
        tuple(coordinate)
        for face in faces
        for ring in (face.exterior, *face.interiors)
        for coordinate in ring.coords
        if silhouette.boundary.distance(Point(coordinate)) <= flattening_tolerance * 2
    )
    match_tolerance = max(flattening_tolerance * 3.0, 0.05)
    intersections = _canonical_split_nodes(
        outline,
        _exact_intersections(outline, crack_lines, boundary_endpoints, match_tolerance),
    )
    internal_by_face = _face_internal_edges(
        faces,
        silhouette,
        intersections,
        max(flattening_tolerance * 2, 0.1),
    )
    exterior = _exterior_edges(
        outline,
        intersections,
        faces,
        max(flattening_tolerance * 2.0, 0.1),
    )
    result = []
    for face_index, fragment_id in enumerate(fragment_ids):
        edges = [
            *[edge for edge in exterior if face_index in edge.faces],
            *internal_by_face[face_index],
        ]
        result.append(_assemble(face_index, faces[face_index], edges, fragment_id))
    return tuple(result)
