from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, replace

from shapely.geometry import LineString, Point
from shapely.ops import polygonize, split, unary_union

from .geometry import (
    UnsupportedOutlineError,
    adaptive_flattening_tolerance,
    geometry_polygons,
    geometry_to_canonical_rings,
    master_contours_to_union,
    normalize_outline,
)
from .hybrid import reconstruct_hybrid_contours
from .model import (
    CubicSegment,
    ComplexityProfile,
    Fragment,
    GenerationResult,
    GenerationSettings,
    GlyphOutline,
    MasterContour,
    MasterGlyph,
    LineSegment,
    master_contour_segments,
)
from .validation import validate_pair

SEED_DERIVATION_VERSION = "sha256-v1"
RECURSIVE_TOPOLOGY_VERSION = "recursive-split-v1"
BRANCHING_TOPOLOGY_V1 = "branching-crack-mesh-v1"
CLEAN_MACRO_COMPARISON_VERSION = "branching-clean-macro-v2"
TOPOLOGY_VERSION = "branching-rough-crack-mesh-v2"
EDGE_PROFILE_VERSION = "independent-rock-edge-detail-v1"
MOTION_ALGORITHM_V1 = "fragment-affine-motion-v1"
MOTION_ALGORITHM_VERSION = "architectural-erosion-v2"
OUTLINE_RECONSTRUCTION_VERSION = "hybrid-source-exterior-v1"


@dataclass(frozen=True)
class EdgeProfileParameters:
    """Bounded micro-profile values; lengths are expressed in font units."""

    edge_subdivision_density: float
    lateral_deviation_amplitude: float
    segment_length_variation: float
    sharp_corner_probability: float
    local_notch_probability: float
    simplification_threshold: float
    minimum_segment_length: float


def edge_profile_parameters(rock_edge_detail: int, upm: float) -> EdgeProfileParameters:
    """Map 0..100 detail to a guarded micro-edge point density.

    Detail controls only how many points from the stable maximum profile are
    active. All values which determine candidate geometry remain constant.
    """

    if isinstance(rock_edge_detail, bool) or not isinstance(rock_edge_detail, int):
        raise ValueError("rock edge detail must be an integer in the range 0..100")
    if not 0 <= rock_edge_detail <= 100:
        raise ValueError("rock edge detail must be in the range 0..100")
    linear = rock_edge_detail / 100.0
    normalized = linear * linear * (3.0 - 2.0 * linear)
    return EdgeProfileParameters(
        edge_subdivision_density=8.0 + 92.0 * normalized,
        lateral_deviation_amplitude=upm * 0.006,
        segment_length_variation=0.48,
        sharp_corner_probability=0.16,
        local_notch_probability=0.08,
        simplification_threshold=upm * 0.00045,
        minimum_segment_length=upm * 0.003,
    )


def derive_effective_seed(settings: GenerationSettings, glyph_name: str) -> int:
    fields = (
        SEED_DERIVATION_VERSION,
        settings.project_seed,
        glyph_name,
        str(settings.complexity),
        settings.glyph_seed_override or "",
    )
    digest = hashlib.sha256("\x1f".join(fields).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def complexity_profile(value: int, *, area: float, units_per_em: float) -> ComplexityProfile:
    if not 0 <= value <= 100:
        raise ValueError("complexity must be in the range 0..100")
    normalized = value / 100.0
    em_area = units_per_em * units_per_em
    capacity = max(1, min(28, int(area / max(em_area * 0.012, 1.0))))
    target = max(1, min(capacity, round(1 + (capacity - 1) * normalized**1.2)))
    minimum_area = em_area * (0.0048 - 0.0042 * normalized)
    return ComplexityProfile(
        value=value,
        target_fragments=target,
        minimum_area=minimum_area,
        primary_split_count=max(0, round((target - 1) * (0.70 - 0.15 * normalized))),
        secondary_probability=0.08 + 0.42 * normalized,
        chip_probability=0.02 + 0.28 * normalized,
        edge_irregularity=0.10 + 0.40 * normalized,
        detail_depth=1 + round(3 * normalized),
    )


def _geometry_key(geometry) -> tuple:
    return (
        round(geometry.bounds[0], 8),
        round(geometry.bounds[1], 8),
        -round(geometry.area, 8),
        geometry.normalize().wkb_hex,
    )


def _split_piece(
    piece,
    rng: random.Random,
    profile: ComplexityProfile,
    upm: float,
    *,
    chip_mode: bool,
):
    centroid = piece.centroid
    min_x, min_y, max_x, max_y = piece.bounds
    extent = max(max_x - min_x, max_y - min_y, upm * 0.1)
    base_angle = rng.uniform(0, math.pi)
    angle_jitter = (rng.random() - 0.5) * profile.edge_irregularity * math.pi / 2
    angle = base_angle + angle_jitter
    normal_x = -math.sin(angle)
    normal_y = math.cos(angle)
    if chip_mode:
        offset_limit = 0.30 + profile.edge_irregularity * 0.12
    else:
        offset_limit = 0.12 + profile.edge_irregularity * 0.10
    offset = rng.uniform(-offset_limit, offset_limit) * extent
    center_x = centroid.x + normal_x * offset
    center_y = centroid.y + normal_y * offset
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    length = extent * 4 + upm
    cutter = LineString(
        [
            (center_x - direction_x * length, center_y - direction_y * length),
            (center_x + direction_x * length, center_y + direction_y * length),
        ]
    )
    parts = [part for part in split(piece, cutter).geoms if part.area > 0]
    if len(parts) < 2:
        return None
    parts.sort(key=_geometry_key)
    if min(part.area for part in parts) < profile.minimum_area:
        return None
    return parts


def generate_recursive_topology(silhouette, profile: ComplexityProfile, seed: int, upm: float):
    rng = random.Random(seed)
    pieces = geometry_polygons(silhouette)
    initial_piece_count = len(pieces)
    attempts = 0
    maximum_attempts = max(60, profile.target_fragments * (8 + profile.detail_depth * 4))
    while len(pieces) < profile.target_fragments and attempts < maximum_attempts:
        attempts += 1
        candidates = [piece for piece in pieces if piece.area >= profile.minimum_area * 2.15]
        if not candidates:
            break
        completed_splits = len(pieces) - initial_piece_count
        if completed_splits < profile.primary_split_count:
            piece = max(candidates, key=lambda candidate: (candidate.area, _geometry_key(candidate)))
        elif rng.random() < profile.secondary_probability:
            weights = [piece.area**0.78 for piece in candidates]
            piece = rng.choices(candidates, weights=weights, k=1)[0]
        else:
            piece = max(candidates, key=lambda candidate: (candidate.area, _geometry_key(candidate)))
        chip_mode = rng.random() < profile.chip_probability
        result = _split_piece(piece, rng, profile, upm, chip_mode=chip_mode)
        if result is None:
            continue
        pieces.remove(piece)
        pieces.extend(result)
    pieces.sort(key=_geometry_key)
    return tuple(pieces)


def _point_along(line: LineString, fraction: float) -> tuple[float, float]:
    point = line.interpolate(max(0.0, min(1.0, fraction)), normalized=True)
    return point.x, point.y


def _impact_hub(component, rng: random.Random, extent: float) -> Point:
    # A visual impact point may lie in a counter. Requiring filled containment would
    # pin O-like glyphs to one stroke and prevent the web crossing the whole shape.
    min_x, min_y, max_x, max_y = component.bounds
    return Point(
        (min_x + max_x) * 0.5 + rng.uniform(-0.045, 0.045) * extent,
        (min_y + max_y) * 0.5 + rng.uniform(-0.045, 0.045) * extent,
    )


def _component_crack_mesh(
    component,
    target_fragments: int,
    profile: ComplexityProfile,
    rng: random.Random,
    upm: float,
    *,
    shared_secondary_anchors: bool,
) -> tuple[LineString, ...]:
    """Build bounded spiderweb linework; polygon creation happens separately."""
    if target_fragments <= 1:
        return ()
    min_x, min_y, max_x, max_y = component.bounds
    extent = max(math.hypot(max_x - min_x, max_y - min_y), upm * 0.08)
    hub = _impact_hub(component, rng, extent)
    primary_count = min(7, max(2, round(math.sqrt(target_fragments * 1.55))))
    base_angle = rng.uniform(0.0, math.tau)
    nominal_step = math.tau / primary_count
    angles = sorted(
        base_angle
        + index * nominal_step
        + rng.uniform(-0.24, 0.24) * nominal_step
        for index in range(primary_count)
    )

    primary_lines = []
    for angle in angles:
        points = [(hub.x, hub.y)]
        wandering_angle = angle
        for radius in (0.16, 0.34, 0.58, 0.88, 1.55):
            wandering_angle += rng.uniform(-0.10, 0.10) * (0.55 + profile.edge_irregularity)
            radial = extent * radius * rng.uniform(0.91, 1.09)
            tangent = extent * radius * rng.uniform(-0.035, 0.035)
            points.append(
                (
                    hub.x + math.cos(wandering_angle) * radial - math.sin(wandering_angle) * tangent,
                    hub.y + math.sin(wandering_angle) * radial + math.cos(wandering_angle) * tangent,
                )
            )
        primary_lines.append(LineString(points))

    primary_anchors: list[list[tuple[float, float]]] = [
        [] for _ in primary_lines
    ]
    secondary_lines: list[LineString] = []
    # Cross-links between neighbouring primary cracks create the recognisable web.
    extra_needed = max(0, target_fragments - primary_count)
    level_count = min(3, math.ceil(extra_needed / max(primary_count, 1)))
    level_fractions = (0.24, 0.43, 0.64)
    for level in range(level_count):
        fraction = level_fractions[level] * rng.uniform(0.91, 1.09)
        anchors = None
        if shared_secondary_anchors:
            anchors = [
                _point_along(line, fraction * rng.uniform(0.93, 1.07))
                for line in primary_lines
            ]
            for index, anchor in enumerate(anchors):
                primary_anchors[index].append(anchor)
        for index, first in enumerate(primary_lines):
            second = primary_lines[(index + 1) % primary_count]
            if anchors is None:
                start = _point_along(first, fraction * rng.uniform(0.93, 1.07))
                end = _point_along(second, fraction * rng.uniform(0.93, 1.07))
            else:
                start = anchors[index]
                end = anchors[(index + 1) % primary_count]
            midpoint = (
                (start[0] + end[0]) * 0.5 + rng.uniform(-0.055, 0.055) * extent,
                (start[1] + end[1]) * 0.5 + rng.uniform(-0.055, 0.055) * extent,
            )
            secondary_lines.append(LineString((start, midpoint, end)))

    # Make every intended branch junction an explicit vertex in its primary
    # crack. This does not move the macro path; it only removes GEOS ambiguity
    # about a secondary endpoint lying numerically just beside a segment.
    if shared_secondary_anchors:
        noded_primary = []
        for line, anchors in zip(primary_lines, primary_anchors):
            vertices = {
                round(line.project(Point(coordinate)), 9): coordinate
                for coordinate in line.coords
            }
            for anchor in anchors:
                vertices[round(line.project(Point(anchor)), 9)] = anchor
            noded_primary.append(LineString(tuple(vertices[key] for key in sorted(vertices))))
        primary_lines = noded_primary
    lines: list[LineString] = [*primary_lines, *secondary_lines]

    # Small local chips are short boundary-to-boundary branches, not global slices.
    chip_count = min(4, round(profile.value / 25)) if target_fragments > 3 else 0
    boundary = component.exterior
    for _ in range(chip_count):
        center_distance = rng.random() * boundary.length
        span = boundary.length * rng.uniform(0.018, 0.045)
        start = boundary.interpolate((center_distance - span) % boundary.length)
        end = boundary.interpolate((center_distance + span) % boundary.length)
        depth = rng.uniform(0.10, 0.24)
        apex = (
            (start.x + end.x) * 0.5 * (1.0 - depth) + hub.x * depth,
            (start.y + end.y) * 0.5 * (1.0 - depth) + hub.y * depth,
        )
        lines.append(LineString(((start.x, start.y), apex, (end.x, end.y))))
    return tuple(lines)


def _generate_macro_crack_mesh(
    silhouette,
    profile: ComplexityProfile,
    seed: int,
    upm: float,
    *,
    shared_secondary_anchors: bool,
) -> tuple[LineString, ...]:
    """Return deterministic large-scale layout without a micro edge profile."""
    rng = random.Random(seed)
    components = geometry_polygons(silhouette)
    total_area = sum(component.area for component in components)
    desired_total = max(profile.target_fragments, len(components))
    allocations = [1 for _ in components]
    remaining = desired_total - len(components)
    while remaining > 0:
        index = max(
            range(len(components)),
            key=lambda item: (
                components[item].area / total_area * desired_total - allocations[item],
                components[item].area,
                -item,
            ),
        )
        allocations[index] += 1
        remaining -= 1
    lines = []
    for component, allocation in zip(components, allocations):
        lines.extend(
            _component_crack_mesh(
                component,
                allocation,
                profile,
                rng,
                upm,
                shared_secondary_anchors=shared_secondary_anchors,
            )
        )
    return tuple(lines)


def generate_macro_crack_mesh_v1(
    silhouette, profile: ComplexityProfile, seed: int, upm: float
) -> tuple[LineString, ...]:
    return _generate_macro_crack_mesh(
        silhouette,
        profile,
        seed,
        upm,
        shared_secondary_anchors=False,
    )


def generate_macro_crack_mesh(
    silhouette, profile: ComplexityProfile, seed: int, upm: float
) -> tuple[LineString, ...]:
    return _generate_macro_crack_mesh(
        silhouette,
        profile,
        seed,
        upm,
        shared_secondary_anchors=True,
    )


def _macro_break_points(
    line: LineString,
    junctions: tuple[Point, ...],
    minimum_segment_length: float,
) -> tuple[tuple[float, Point], ...]:
    points = {0.0: Point(line.coords[0]), round(line.length, 9): Point(line.coords[-1])}
    for junction in junctions:
        if junction.distance(line) <= 1e-6:
            points[round(line.project(junction), 9)] = junction
    travelled = 0.0
    coordinates = list(line.coords)
    for first, second in zip(coordinates, coordinates[1:]):
        travelled += math.hypot(second[0] - first[0], second[1] - first[1])
        # Every original macro vertex is mandatory. In particular, detail must
        # never straighten away a macro bend merely because its minimum-segment
        # threshold changed.
        points[round(travelled, 9)] = Point(second)
    return tuple(sorted(points.items()))


def _mesh_incidence_graph(lines: tuple[LineString, ...]) -> tuple[bool, ...]:
    """Record which macro edges meet, with the existing numerical tolerance."""

    return tuple(
        lines[first].distance(lines[second]) <= 1e-6
        for first in range(len(lines))
        for second in range(first)
    )


def _intersection_signature(first: LineString, second: LineString) -> tuple:
    intersection = first.intersection(second)
    return (
        intersection.geom_type,
        len(_point_intersections(intersection)),
        round(intersection.length, 7),
    )


def _mesh_intersection_signature(lines: tuple[LineString, ...]) -> tuple[tuple, ...]:
    signature = []
    for first, line in enumerate(lines):
        for other in lines[:first]:
            signature.append(_intersection_signature(line, other))
    return tuple(signature)


def _point_intersections(geometry) -> tuple[Point, ...]:
    if geometry.is_empty:
        return ()
    if geometry.geom_type == "Point":
        return (geometry,)
    if geometry.geom_type == "MultiPoint":
        return tuple(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        return tuple(
            point
            for part in geometry.geoms
            for point in _point_intersections(part)
        )
    return ()


def _roughen_span(
    start: Point,
    end: Point,
    parameters: EdgeProfileParameters,
    rng: random.Random,
    upm: float,
    amplitude_scale: float,
    rock_edge_detail: int,
    rock_edge_roughness: int = 100,
    offset_scale=None,
) -> list[tuple[float, float]]:
    dx = end.x - start.x
    dy = end.y - start.y
    length = math.hypot(dx, dy)
    if length <= parameters.minimum_segment_length * 1.5:
        return [(start.x, start.y), (end.x, end.y)]
    direction = (dx / length, dy / length)
    normal = (-direction[1], direction[0])
    roughness_scale = rock_edge_roughness / 100.0
    # Always construct the same maximum-detail candidates. Detail only filters
    # this sequence after every coordinate and displacement has been fixed.
    maximum_density = edge_profile_parameters(100, upm).edge_subdivision_density
    nominal_length = upm / maximum_density
    distances = [0.0]
    cursor = 0.0
    while length - cursor > nominal_length * 1.35:
        varied = nominal_length * rng.uniform(
            1.0 - parameters.segment_length_variation,
            1.0 + parameters.segment_length_variation,
        )
        step = max(parameters.minimum_segment_length, varied)
        if length - (cursor + step) < parameters.minimum_segment_length:
            break
        cursor += step
        distances.append(cursor)
    distances.append(length)

    candidates = []
    candidate_distances = []
    previous_offset = 0.0
    previous_distance = 0.0
    notch_rebound = 0.0
    normalized_length = min(1.0, length / (upm * 0.12))
    smooth_length = normalized_length * normalized_length * (3.0 - 2.0 * normalized_length)
    visible_floor = upm * 0.005
    nominal_amplitude = upm * 0.006
    safety_scale = parameters.lateral_deviation_amplitude / nominal_amplitude
    length_scaled_amplitude = visible_floor + (
        nominal_amplitude - visible_floor
    ) * smooth_length
    span_amplitude = min(length_scaled_amplitude, length * 0.30) * safety_scale
    for distance in distances[1:-1]:
        amplitude = span_amplitude * amplitude_scale
        random_offset = rng.uniform(-1.0, 1.0)
        minimum_offset_fraction = 0.30 * (1.0 - smooth_length)
        offset_fraction = math.copysign(
            minimum_offset_fraction
            + (1.0 - minimum_offset_fraction) * abs(random_offset),
            random_offset,
        )
        independent = amplitude * offset_fraction
        offset = previous_offset * rng.uniform(0.12, 0.48) + independent
        if notch_rebound:
            offset += notch_rebound
            notch_rebound = 0.0
        if rng.random() < parameters.sharp_corner_probability:
            shoulder_direction = -1.0 if rng.random() < 0.5 else 1.0
            offset += shoulder_direction * amplitude * rng.uniform(0.75, 1.45)
        if rng.random() < parameters.local_notch_probability:
            notch_direction = -1.0 if rng.random() < 0.5 else 1.0
            notch_size = notch_direction * amplitude * rng.uniform(1.25, 1.9)
            offset += notch_size
            notch_rebound = -notch_size * rng.uniform(0.45, 0.75)
        offset = max(-amplitude * 2.2, min(amplitude * 2.2, offset))
        along_jitter = rng.uniform(-0.12, 0.12) * nominal_length
        local_distance = min(length - parameters.minimum_segment_length, distance + along_jitter)
        local_distance = max(previous_distance + parameters.minimum_segment_length, local_distance)
        if local_distance >= length - parameters.minimum_segment_length * 0.5:
            continue
        base_point = (
            start.x + direction[0] * local_distance,
            start.y + direction[1] * local_distance,
        )
        local_scale = offset_scale(base_point) if offset_scale is not None else 1.0
        # Derive the second vector component without consuming the established
        # Detail RNG stream. Candidate distances, activation thresholds and
        # all existing perpendicular values therefore remain independent of
        # Roughness. The full 2D vector is fixed before the slider scale is
        # applied.
        tangent_payload = repr((rng.getstate(), distance, local_distance)).encode("ascii")
        tangent_digest = hashlib.sha256(tangent_payload).digest()
        tangent_unit = int.from_bytes(tangent_digest[:8], "big") / (2**64 - 1)
        tangent_offset = (tangent_unit * 2.0 - 1.0) * amplitude * 0.35
        offset *= local_scale
        tangent_offset *= local_scale
        candidate = (
            base_point[0]
            + roughness_scale * (normal[0] * offset + direction[0] * tangent_offset),
            base_point[1]
            + roughness_scale * (normal[1] * offset + direction[1] * tangent_offset),
        )
        candidates.append(candidate)
        candidate_distances.append(local_distance)
        previous_offset = offset
        previous_distance = local_distance
    # Endpoint eligibility belongs to the clean Detail schedule. Measuring the
    # displaced coordinate here made Roughness alter point count.
    while candidates and length - candidate_distances[-1] < parameters.minimum_segment_length:
        candidates.pop()
        candidate_distances.pop()

    # Activate candidates from coarse to fine. At each rank, select the point
    # furthest from the already active distances, so low values retain long,
    # well-distributed segments and every higher value is a strict superset.
    remaining = set(range(len(candidates)))
    active_distances = [0.0, length]
    activation_rank = {}
    while remaining:
        selected = max(
            remaining,
            key=lambda index: (
                min(
                    abs(candidate_distances[index] - active)
                    for active in active_distances
                ),
                -index,
            ),
        )
        activation_rank[selected] = len(activation_rank) + 1
        active_distances.append(candidate_distances[selected])
        remaining.remove(selected)
    activation_thresholds = {
        index: math.ceil(rank * 100 / len(candidates))
        for index, rank in activation_rank.items()
    }
    points = [(start.x, start.y)]
    points.extend(
        candidate
        for index, candidate in enumerate(candidates)
        if activation_thresholds[index] <= rock_edge_detail
    )
    points.append((end.x, end.y))
    return points


def _roughen_crack_mesh_once(
    macro_lines: tuple[LineString, ...],
    silhouette,
    profile: ComplexityProfile,
    seed: int,
    upm: float,
    *,
    rock_edge_detail: int,
    rock_edge_roughness: int = 100,
    parameters: EdgeProfileParameters | None = None,
) -> tuple[LineString, ...]:
    """Apply micro-edge detail while preserving endpoints and mesh junctions."""
    if rock_edge_detail == 0:
        return macro_lines
    parameters = parameters or edge_profile_parameters(profile.value, upm)
    boundary_guard = 2.2 * upm / edge_profile_parameters(
        100,
        upm,
    ).edge_subdivision_density
    junctions = tuple(
        Point(coordinate)
        for line in macro_lines
        for coordinate in (line.coords[0], line.coords[-1])
    ) + tuple(
        point
        for first, line in enumerate(macro_lines)
        for other in macro_lines[:first]
        for point in _point_intersections(line.intersection(other))
        if silhouette.covers(point)
    )
    roughened = []
    safety_roughened = []
    for line_index, line in enumerate(macro_lines):
        break_points = _macro_break_points(
            line,
            junctions,
            parameters.minimum_segment_length,
        )
        candidate = line
        safety_candidate = line
        for attempt in range(4):
            payload = (
                f"rough-edge-v1|{seed}|{line_index}|{attempt}|{line.normalize().wkb_hex}"
            )
            edge_seed = int.from_bytes(
                hashlib.sha256(payload.encode("ascii")).digest()[:8], "big"
            )

            def build(detail, roughness):
                rng = random.Random(edge_seed)
                coordinates = []
                for (_, start), (_, end) in zip(break_points, break_points[1:]):
                    span_line = LineString(
                        ((start.x, start.y), (end.x, end.y))
                    )
                    boundary_intersection = span_line.intersection(
                        silhouette.boundary
                    )
                    boundary_crossings = _point_intersections(
                        boundary_intersection
                    )
                    follows_boundary = (
                        boundary_intersection.length > 1e-7
                    )
                    span_boundary_distance = span_line.distance(
                        silhouette.boundary
                    )

                    def interior_offset_scale(base_point):
                        point = Point(base_point)
                        if not silhouette.covers(point):
                            return 0.0
                        if follows_boundary:
                            return 0.0
                        if (
                            not boundary_crossings
                            and span_boundary_distance > upm * 0.001
                        ):
                            return 1.0
                        distance = (
                            min(
                                point.distance(crossing)
                                for crossing in boundary_crossings
                            )
                            if boundary_crossings
                            else point.distance(silhouette.boundary)
                        )
                        if distance <= boundary_guard:
                            return 0.0
                        fade = min(1.0, (distance - boundary_guard) / boundary_guard)
                        return fade * fade * (3.0 - 2.0 * fade)

                    span = _roughen_span(
                        start,
                        end,
                        parameters,
                        rng,
                        upm,
                        amplitude_scale=0.55**attempt,
                        rock_edge_detail=detail,
                        rock_edge_roughness=roughness,
                        offset_scale=interior_offset_scale,
                    )
                    coordinates.extend(span if not coordinates else span[1:])
                return LineString(coordinates)

            # Safety always selects against the same full-detail/full-vector
            # reference. Roughness therefore cannot choose a new edge seed or
            # fallback amplitude.
            maximum_candidate = build(100, 100)
            comparison_lines = (
                *enumerate(safety_roughened),
                *(
                    (other_index, macro_lines[other_index])
                    for other_index in range(line_index + 1, len(macro_lines))
                ),
            )
            intersections_stable = all(
                _intersection_signature(maximum_candidate, other)
                == _intersection_signature(line, macro_lines[other_index])
                for other_index, other in comparison_lines
            )
            if maximum_candidate.is_simple and intersections_stable:
                safety_candidate = maximum_candidate
                candidate = (
                    maximum_candidate
                    if rock_edge_detail == 100 and rock_edge_roughness == 100
                    else build(rock_edge_detail, rock_edge_roughness)
                )
                break
        if not candidate.is_simple:
            candidate = line
        roughened.append(candidate)
        safety_roughened.append(safety_candidate)
    return tuple(roughened)


def generate_crack_mesh(
    silhouette,
    profile: ComplexityProfile,
    seed: int,
    upm: float,
    rock_edge_detail: int = 50,
    rock_edge_roughness: int = 50,
) -> tuple[LineString, ...]:
    """Return the macro layout with its deterministic rough edge profile applied."""
    crack_lines, _ = _profiled_crack_topology(
        silhouette,
        profile,
        seed,
        upm,
        rock_edge_detail,
        rock_edge_roughness,
    )
    return crack_lines


def _merge_fragments(pieces: list, target: int, minimum_area: float) -> list:
    def merge_candidate(index: int):
        neighbours = []
        for other_index, other in enumerate(pieces):
            if other_index == index:
                continue
            shared = pieces[index].boundary.intersection(other.boundary).length
            if shared > 1e-7:
                neighbours.append((shared, -other.area, other_index))
        return max(neighbours)[2] if neighbours else None

    while len(pieces) > target or any(piece.area < minimum_area for piece in pieces):
        undersized = [i for i, piece in enumerate(pieces) if piece.area < minimum_area]
        if undersized:
            index = min(undersized, key=lambda item: (pieces[item].area, _geometry_key(pieces[item])))
        elif len(pieces) > target:
            index = min(range(len(pieces)), key=lambda item: (pieces[item].area, _geometry_key(pieces[item])))
        else:
            break
        neighbour = merge_candidate(index)
        if neighbour is None:
            break
        merged = pieces[index].union(pieces[neighbour])
        for remove_index in sorted((index, neighbour), reverse=True):
            pieces.pop(remove_index)
        pieces.extend(geometry_polygons(merged))
    return pieces


def _topology_from_crack_lines(silhouette, profile, crack_lines, upm: float):
    if not crack_lines:
        return tuple(sorted(geometry_polygons(silhouette), key=_geometry_key))
    linework = unary_union([silhouette.boundary, *crack_lines])
    faces = [
        face
        for face in polygonize(linework)
        if face.area > 0 and silhouette.covers(face.representative_point())
    ]
    pieces = _merge_fragments(
        faces,
        max(profile.target_fragments, len(geometry_polygons(silhouette))),
        profile.minimum_area,
    )
    reconstructed = unary_union(pieces)
    tolerance_area = max(upm * upm * 1e-8, silhouette.area * 1e-8)
    if reconstructed.symmetric_difference(silhouette).area > tolerance_area:
        raise RuntimeError("branching crack mesh did not preserve the normalized silhouette")
    pieces.sort(key=_geometry_key)
    return tuple(pieces)


def _piece_adjacency(pieces: tuple) -> frozenset[tuple[int, int]]:
    return frozenset(
        (second, first)
        for first in range(len(pieces))
        for second in range(first)
        if pieces[first].boundary.intersection(pieces[second].boundary).length > 1e-7
    )


def _map_profiled_pieces_to_macro(macro_pieces: tuple, profiled_pieces: tuple):
    """Return profiled faces in canonical macro order, or None if structure moved."""

    if len(macro_pieces) != len(profiled_pieces):
        return None
    remaining = set(range(len(profiled_pieces)))
    mapping = []
    for macro_piece in macro_pieces:
        if not remaining:
            return None
        candidate = max(
            remaining,
            key=lambda index: macro_piece.intersection(profiled_pieces[index]).area,
        )
        overlap = macro_piece.intersection(profiled_pieces[candidate]).area
        if overlap <= min(macro_piece.area, profiled_pieces[candidate].area) * 0.5:
            return None
        mapping.append(candidate)
        remaining.remove(candidate)
    remapped_adjacency = frozenset(
        tuple(sorted((mapping.index(first), mapping.index(second))))
        for first, second in _piece_adjacency(profiled_pieces)
    )
    if remapped_adjacency != _piece_adjacency(macro_pieces):
        return None
    return tuple(profiled_pieces[index] for index in mapping)


def _profiled_crack_topology(
    silhouette,
    profile: ComplexityProfile,
    seed: int,
    upm: float,
    rock_edge_detail: int,
    rock_edge_roughness: int,
):
    """Return one edge profile and its faces without changing macro structure."""

    if isinstance(rock_edge_roughness, bool) or not isinstance(rock_edge_roughness, int):
        raise ValueError("rock edge roughness must be an integer in the range 0..100")
    if not 0 <= rock_edge_roughness <= 100:
        raise ValueError("rock edge roughness must be in the range 0..100")

    macro_lines = generate_macro_crack_mesh(silhouette, profile, seed, upm)
    macro_pieces = _topology_from_crack_lines(silhouette, profile, macro_lines, upm)
    parameters = edge_profile_parameters(rock_edge_detail, upm)
    macro_intersections = _mesh_incidence_graph(macro_lines)
    macro_intersection_signature = _mesh_intersection_signature(macro_lines)

    def mapped_profile(lines):
        if _mesh_incidence_graph(lines) != macro_intersections:
            return None
        if _mesh_intersection_signature(lines) != macro_intersection_signature:
            return None
        try:
            pieces = _topology_from_crack_lines(
                silhouette,
                profile,
                lines,
                upm,
            )
        except RuntimeError:
            return None
        return _map_profiled_pieces_to_macro(macro_pieces, pieces)

    for attempt in range(10):
        scaled = replace(
            parameters,
            lateral_deviation_amplitude=(
                parameters.lateral_deviation_amplitude * 0.5**attempt
            ),
            simplification_threshold=(
                parameters.simplification_threshold * 0.5**attempt
            ),
        )
        maximum_lines = _roughen_crack_mesh_once(
            macro_lines,
            silhouette,
            profile,
            seed,
            upm,
            rock_edge_detail=100,
            rock_edge_roughness=100,
            parameters=scaled,
        )
        maximum_mapped = mapped_profile(maximum_lines)
        if maximum_mapped is None:
            continue
        # Choose amplitude fallback from fixed reference schedules, never from
        # the requested Detail value. This keeps every slider value on the
        # same candidate coordinates and activation thresholds.
        midpoint_lines = _roughen_crack_mesh_once(
            macro_lines,
            silhouette,
            profile,
            seed,
            upm,
            rock_edge_detail=50,
            rock_edge_roughness=100,
            parameters=scaled,
        )
        if mapped_profile(midpoint_lines) is None:
            continue
        roughness_references = {
            value: _roughen_crack_mesh_once(
                macro_lines,
                silhouette,
                profile,
                seed,
                upm,
                rock_edge_detail=rock_edge_detail,
                rock_edge_roughness=value,
                parameters=scaled,
            )
            for value in (0, 50, 100)
        }
        mapped_references = {
            value: mapped_profile(lines)
            for value, lines in roughness_references.items()
        }
        if all(mapped is not None for mapped in mapped_references.values()):
            candidate_lines = (
                roughness_references[rock_edge_roughness]
                if rock_edge_roughness in roughness_references
                else _roughen_crack_mesh_once(
                    macro_lines,
                    silhouette,
                    profile,
                    seed,
                    upm,
                    rock_edge_detail=rock_edge_detail,
                    rock_edge_roughness=rock_edge_roughness,
                    parameters=scaled,
                )
            )
            mapped = mapped_profile(candidate_lines)
            if mapped is not None:
                return candidate_lines, mapped
    return macro_lines, macro_pieces


def generate_branching_topology_v1(
    silhouette, profile: ComplexityProfile, seed: int, upm: float
):
    """Preserve the clean macro-edge language recorded by existing v1 projects."""
    crack_lines = generate_macro_crack_mesh_v1(silhouette, profile, seed, upm)
    return _topology_from_crack_lines(silhouette, profile, crack_lines, upm)


def generate_clean_macro_topology(
    silhouette, profile: ComplexityProfile, seed: int, upm: float
):
    crack_lines = generate_macro_crack_mesh(silhouette, profile, seed, upm)
    return _topology_from_crack_lines(silhouette, profile, crack_lines, upm)


def generate_topology(
    silhouette,
    profile: ComplexityProfile,
    seed: int,
    upm: float,
    rock_edge_detail: int = 50,
    rock_edge_roughness: int = 50,
):
    _, pieces = _profiled_crack_topology(
        silhouette,
        profile,
        seed,
        upm,
        rock_edge_detail,
        rock_edge_roughness,
    )
    return pieces


def boundary_point_provenance(
    silhouette,
    pieces,
    crack_lines,
    *,
    distance_tolerance: float,
) -> dict:
    """Classify unique fragment vertices which lie on the normalized boundary."""
    source_vertices = []
    for polygon in geometry_polygons(silhouette):
        for ring in (polygon.exterior, *polygon.interiors):
            source_vertices.extend(Point(point) for point in list(ring.coords)[:-1])

    intersections = []
    for line in crack_lines:
        geometry = line.intersection(silhouette.boundary)
        stack = [geometry]
        while stack:
            item = stack.pop()
            if item.is_empty:
                continue
            if item.geom_type == "Point":
                intersections.append(item)
            elif hasattr(item, "geoms"):
                stack.extend(item.geoms)
            elif item.geom_type in {"LineString", "LinearRing"}:
                coords = list(item.coords)
                intersections.extend((Point(coords[0]), Point(coords[-1])))

    candidates = {}
    precision = max(distance_tolerance, 1e-7)
    for piece in pieces:
        for _, points in geometry_to_canonical_rings(piece):
            for point in points:
                candidate = Point(point)
                if candidate.distance(silhouette.boundary) <= distance_tolerance:
                    key = (round(point[0] / precision), round(point[1] / precision))
                    candidates[key] = candidate

    required = []
    baseline = []
    artifacts = []
    match_tolerance = distance_tolerance * 5
    for candidate in candidates.values():
        if any(candidate.distance(point) <= match_tolerance for point in intersections):
            required.append((candidate.x, candidate.y))
        elif any(candidate.distance(point) <= match_tolerance for point in source_vertices):
            baseline.append((candidate.x, candidate.y))
        else:
            artifacts.append((candidate.x, candidate.y))
    return {
        "requiredCrackBoundaryPoints": tuple(sorted(required)),
        "baselineFlatteningBoundaryPoints": tuple(sorted(baseline)),
        "clippingArtifactBoundaryPoints": tuple(sorted(artifacts)),
    }


def _fragment_identifier(seed: int, index: int, geometry, topology_version: str) -> str:
    payload = f"{topology_version}|{seed}|{index}|{geometry.normalize().wkb_hex}"
    return "fr-" + hashlib.sha256(payload.encode("ascii")).hexdigest()[:20]


def _contours_for_fragment(fragment_id: str, geometry) -> tuple[MasterContour, ...]:
    contours = []
    for index, (is_hole, points) in enumerate(geometry_to_canonical_rings(geometry)):
        contour_id = f"{fragment_id}-c{index}"
        point_ids = tuple(f"{fragment_id}-c{index}-p{point_index}" for point_index in range(len(points)))
        contours.append(
            MasterContour(
                identifier=contour_id,
                fragment_id=fragment_id,
                part_index=index,
                is_hole=is_hole,
                points=points,
                point_ids=point_ids,
            )
        )
    return tuple(contours)


def _motion_for_fragment_v1(
    fragment_area: float,
    fragment_id: str,
    settings: GenerationSettings,
    silhouette_area: float,
    upm: float,
):
    digest = hashlib.sha256(f"motion-v1|{fragment_id}".encode("ascii")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    size_ratio = max(0.0, min(1.0, fragment_area / silhouette_area))
    smallness = 1.0 - math.sqrt(size_ratio)
    direction = math.radians(
        settings.movement_direction_degrees
        + rng.uniform(-settings.movement_spread_degrees, settings.movement_spread_degrees)
    )
    distance = upm * 0.16 * settings.erosion_amount * (0.2 + 0.8 * smallness) * rng.uniform(0.35, 1.0)
    translation = (math.cos(direction) * distance, math.sin(direction) * distance)
    rotation = settings.maximum_rotation_degrees * smallness * rng.uniform(-1.0, 1.0)
    scale_loss = (1.0 - settings.minimum_scale) * smallness * rng.uniform(0.2, 1.0)
    scale = max(settings.minimum_scale, 1.0 - scale_loss)
    return translation, rotation, scale


def _architectural_motion_for_fragments(
    fragments: tuple[Fragment, ...],
    settings: GenerationSettings,
    silhouette_area: float,
    upm: float,
) -> dict[str, tuple[tuple[float, float], float, float]]:
    """Return deterministic, size-aware erosion motion with baseline safeguards."""

    if not fragments:
        return {}
    maximum_area = max(fragment.area for fragment in fragments)
    motions = {}
    transformed_minimum_y = {}
    size_classes = {}
    for fragment in fragments:
        digest = hashlib.sha256(
            f"{MOTION_ALGORITHM_VERSION}|{fragment.identifier}".encode("ascii")
        ).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        relative_size = fragment.area / maximum_area
        silhouette_share = max(0.0, min(1.0, fragment.area / silhouette_area))
        smallness = 1.0 - math.sqrt(silhouette_share)
        if relative_size >= 0.55:
            size_class = "large"
            movement_multiplier = settings.large_fragment_movement_multiplier
        elif relative_size >= 0.20:
            size_class = "medium"
            movement_multiplier = settings.medium_fragment_movement_multiplier
        else:
            size_class = "small"
            movement_multiplier = settings.small_fragment_movement_multiplier
        size_classes[fragment.identifier] = size_class

        # The largest piece is the structural core. It still participates in the
        # master, but its translation, rotation, and scale loss remain subdued.
        core_factor = 0.35 if fragment.area == maximum_area else 1.0
        direction = math.radians(
            settings.movement_direction_degrees
            + rng.uniform(-settings.movement_spread_degrees, settings.movement_spread_degrees)
        )
        distance = (
            upm
            * 0.12
            * settings.erosion_amount
            * (0.22 + 0.78 * smallness)
            * rng.uniform(0.30, 1.0)
            * movement_multiplier
            * core_factor
        )
        translation_x = math.cos(direction) * distance
        translation_y = math.sin(direction) * distance

        downward_limit = upm * settings.maximum_downward_drift_em
        translation_y = max(translation_y, -downward_limit)
        if translation_y < 0:
            proximity = 1.0 - max(
                0.0,
                min(1.0, max(fragment.bounds[1], 0.0) / max(upm * 0.08, 1.0)),
            )
            translation_y *= 1.0 - settings.baseline_retention * proximity

        rotation = (
            settings.maximum_rotation_degrees
            * smallness
            * movement_multiplier
            * core_factor
            * rng.uniform(-1.0, 1.0)
        )
        scale_loss = (
            (1.0 - settings.minimum_scale)
            * smallness
            * min(1.0, movement_multiplier)
            * core_factor
            * rng.uniform(0.15, 0.85)
        )
        scale = max(settings.minimum_scale, 1.0 - scale_loss)
        translation = (translation_x, translation_y)
        motions[fragment.identifier] = (translation, rotation, scale)
        transformed = (
            _transform_contour(
                contour,
                fragment.transform_origin,
                translation,
                rotation,
                scale,
            )
            for contour in fragment.intact_contours
        )
        transformed_minimum_y[fragment.identifier] = min(
            point[1] for contour in transformed for point in contour.points
        )

    # Only fragments whose original geometry is on/above the baseline count as
    # newly crossing it. Prefer the smallest chips when a bounded crossing is
    # allowed, and lift all other candidates exactly back to the baseline.
    crossing = [
        fragment
        for fragment in fragments
        if fragment.bounds[1] >= -1e-7
        and transformed_minimum_y[fragment.identifier] < -1e-7
    ]
    crossing.sort(
        key=lambda fragment: (
            {"small": 0, "medium": 1, "large": 2}[size_classes[fragment.identifier]],
            fragment.area,
            fragment.identifier,
        )
    )
    allowed_count = math.floor(
        len(fragments) * settings.maximum_baseline_crossing_fraction
    )
    for fragment in crossing[allowed_count:]:
        translation, rotation, scale = motions[fragment.identifier]
        lift = -transformed_minimum_y[fragment.identifier]
        motions[fragment.identifier] = (
            (translation[0], translation[1] + lift),
            rotation,
            scale,
        )
    return motions


def _motions_for_fragments(
    fragments: tuple[Fragment, ...],
    settings: GenerationSettings,
    silhouette_area: float,
    upm: float,
    motion_algorithm_version: str,
):
    if motion_algorithm_version == MOTION_ALGORITHM_VERSION:
        return _architectural_motion_for_fragments(
            fragments, settings, silhouette_area, upm
        )
    if motion_algorithm_version == MOTION_ALGORITHM_V1:
        return {
            fragment.identifier: _motion_for_fragment_v1(
                fragment.area,
                fragment.identifier,
                settings,
                silhouette_area,
                upm,
            )
            for fragment in fragments
        }
    raise ValueError(f"unsupported motion algorithm: {motion_algorithm_version}")


def _transform_contour(contour: MasterContour, origin, translation, rotation_degrees, scale):
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    def transform(point):
        x, y = point
        local_x = (x - origin[0]) * scale
        local_y = (y - origin[1]) * scale
        return (
            origin[0] + local_x * cosine - local_y * sine + translation[0],
            origin[1] + local_x * sine + local_y * cosine + translation[1],
        )

    transformed_segments = []
    for segment in master_contour_segments(contour):
        if isinstance(segment, CubicSegment):
            transformed_segments.append(
                CubicSegment(
                    transform(segment.start),
                    transform(segment.control1),
                    transform(segment.control2),
                    transform(segment.end),
                )
            )
        else:
            transformed_segments.append(
                LineSegment(transform(segment.start), transform(segment.end))
            )
    return replace(
        contour,
        points=tuple(segment.end for segment in transformed_segments),
        segments=tuple(transformed_segments),
    )


def generate_pair(
    outline: GlyphOutline,
    settings: GenerationSettings,
    *,
    topology_generator=generate_topology,
    topology_version: str = TOPOLOGY_VERSION,
    motion_algorithm_version: str = MOTION_ALGORITHM_VERSION,
) -> GenerationResult:
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    source_rings, silhouette, normalization = normalize_outline(outline, tolerance)
    crossing_contours = any(
        LineString((*source_rings[first], source_rings[first][0])).intersects(
            LineString((*source_rings[second], source_rings[second][0]))
        )
        for first in range(len(source_rings))
        for second in range(first)
    )
    if topology_generator is generate_topology and (
        normalization.normalization_applied
        or normalization.self_intersecting_contours
        or crossing_contours
    ):
        raise UnsupportedOutlineError(
            "hybrid cubic reconstruction does not support overlapping or self-intersecting source contours"
        )
    profile = complexity_profile(
        settings.complexity,
        area=silhouette.area,
        units_per_em=outline.units_per_em,
    )
    seed = derive_effective_seed(settings, outline.name)
    if topology_generator is generate_topology:
        canonical_pieces = generate_clean_macro_topology(
            silhouette,
            profile,
            seed,
            outline.units_per_em,
        )
        crack_lines, pieces = _profiled_crack_topology(
            silhouette,
            profile,
            seed,
            outline.units_per_em,
            settings.rock_edge_detail,
            settings.rock_edge_roughness,
        )
    else:
        pieces = topology_generator(silhouette, profile, seed, outline.units_per_em)
        canonical_pieces = pieces
        crack_lines = None

    if len(pieces) != len(canonical_pieces):
        raise RuntimeError("edge profiling changed the canonical fragment count")

    fragment_ids = tuple(
        _fragment_identifier(seed, index, macro_piece, topology_version)
        for index, macro_piece in enumerate(canonical_pieces)
    )
    hybrid_contours = None
    if topology_generator is generate_topology:
        hybrid_contours = reconstruct_hybrid_contours(
            outline,
            pieces,
            crack_lines,
            fragment_ids,
            flattening_tolerance=tolerance,
        )

    canonical_fragments = []
    intact_contours = []
    for index, (piece, macro_piece) in enumerate(zip(pieces, canonical_pieces)):
        # Identity and all motion-driving metrics belong to the clean macro
        # face. Rock Edge Detail may alter only the contour drawn around it.
        fragment_id = fragment_ids[index]
        canonical = (
            hybrid_contours[index]
            if hybrid_contours is not None
            else _contours_for_fragment(fragment_id, piece)
        )
        origin = (macro_piece.centroid.x, macro_piece.centroid.y)
        canonical_fragments.append(
            Fragment(
                identifier=fragment_id,
                area=macro_piece.area,
                centroid=origin,
                bounds=macro_piece.bounds,
                transform_origin=origin,
                intact_contours=canonical,
                translation=(0.0, 0.0),
                rotation_degrees=0.0,
                scale=1.0,
            )
        )
        intact_contours.extend(canonical)
    canonical_fragments = tuple(canonical_fragments)
    motions = _motions_for_fragments(
        canonical_fragments,
        settings,
        silhouette.area,
        outline.units_per_em,
        motion_algorithm_version,
    )
    fragments = []
    eroded_contours = []
    for fragment in canonical_fragments:
        translation, rotation, scale = motions[fragment.identifier]
        moved = tuple(
            _transform_contour(
                contour,
                fragment.transform_origin,
                translation,
                rotation,
                scale,
            )
            for contour in fragment.intact_contours
        )
        fragments.append(
            replace(
                fragment,
                translation=translation,
                rotation_degrees=rotation,
                scale=scale,
            )
        )
        eroded_contours.extend(moved)

    intact = MasterGlyph(outline.name, outline.width, outline.unicodes, tuple(intact_contours))
    eroded = MasterGlyph(outline.name, outline.width, outline.unicodes, tuple(eroded_contours))
    # Hybrid contours are authoritative on the exterior. Their fine-flattened
    # union avoids treating the coarser fracture-classification proxy as truth.
    validation_source = (
        master_contours_to_union(intact.contours, tolerance=tolerance * 0.02)
        if hybrid_contours is not None
        else silhouette
    )
    report = validate_pair(
        source_silhouette=validation_source,
        intact=intact,
        eroded=eroded,
        units_per_em=outline.units_per_em,
        minimum_area=profile.minimum_area,
    )
    notes = (
        "Original cubic and line segments are preserved on the exterior; generated line segments occur only on fracture edges.",
        "Complexity changes deterministically regenerate topology; refinement is not nested.",
    )
    return GenerationResult(
        glyph_name=outline.name,
        effective_seed=seed,
        flattening_tolerance=tolerance,
        rock_edge_detail=settings.rock_edge_detail,
        rock_edge_roughness=settings.rock_edge_roughness,
        profile=profile,
        normalization=normalization,
        fragments=tuple(fragments),
        intact=intact,
        eroded=eroded,
        validation=report,
        notes=notes,
        outline_reconstruction_version=(
            OUTLINE_RECONSTRUCTION_VERSION
            if hybrid_contours is not None
            else "polygonal-v1"
        ),
    )


def regenerate_motion_from_topology(
    topology: GenerationResult,
    settings: GenerationSettings,
    *,
    units_per_em: float,
    motion_algorithm_version: str = MOTION_ALGORITHM_VERSION,
) -> GenerationResult:
    """Reuse canonical intact fragments while recalculating motion only."""

    source_silhouette = master_contours_to_union(topology.intact.contours)
    motions = _motions_for_fragments(
        topology.fragments,
        settings,
        source_silhouette.area,
        units_per_em,
        motion_algorithm_version,
    )
    fragments = []
    eroded_contours = []
    for fragment in topology.fragments:
        translation, rotation, scale = motions[fragment.identifier]
        moved = tuple(
            _transform_contour(
                contour,
                fragment.transform_origin,
                translation,
                rotation,
                scale,
            )
            for contour in fragment.intact_contours
        )
        fragments.append(
            replace(
                fragment,
                translation=translation,
                rotation_degrees=rotation,
                scale=scale,
            )
        )
        eroded_contours.extend(moved)

    eroded = MasterGlyph(
        topology.intact.name,
        topology.intact.width,
        topology.intact.unicodes,
        tuple(eroded_contours),
    )
    report = validate_pair(
        source_silhouette=source_silhouette,
        intact=topology.intact,
        eroded=eroded,
        units_per_em=units_per_em,
        minimum_area=topology.profile.minimum_area,
    )
    return replace(
        topology,
        fragments=tuple(fragments),
        eroded=eroded,
        validation=report,
    )
