from __future__ import annotations

from dataclasses import replace
import math
from time import perf_counter

import pytest
from shapely.geometry import Point

from fracturize import GenerationSettings, generate_pair
from fracturize.core import (
    MOTION_ALGORITHM_V1,
    MOTION_ALGORITHM_VERSION,
    boundary_point_provenance,
    complexity_profile,
    derive_effective_seed,
    edge_profile_parameters,
    generate_crack_mesh,
    generate_macro_crack_mesh,
    generate_topology,
    regenerate_motion_from_topology,
)
from test_support.fixtures import component_fixture, proof_fixtures
from fracturize.geometry import (
    UnsupportedOutlineError,
    adaptive_flattening_tolerance,
    master_contours_to_union,
    normalize_outline,
)
from fracturize.model import MasterContour, MasterGlyph
from fracturize.validation import validate_pair


@pytest.mark.parametrize("glyph_name", tuple(proof_fixtures()))
def test_supported_fixtures_reconstruct_and_are_compatible(glyph_name):
    result = generate_pair(proof_fixtures()[glyph_name], GenerationSettings(complexity=50))
    assert result.validation.compatible
    assert result.validation.reconstruction.normalized_symmetric_difference <= 1e-8
    assert result.validation.reconstruction.hausdorff_distance <= 0.0001
    assert result.intact.width == result.eroded.width
    assert result.intact.contours
    assert len(result.intact.contours) == len(result.eroded.contours)


def test_same_inputs_generate_identical_topology_and_motion():
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(project_seed="repeatable", complexity=75)
    first = generate_pair(outline, settings)
    second = generate_pair(outline, settings)
    assert first.effective_seed == second.effective_seed
    assert first.fragments == second.fragments
    assert first.intact == second.intact
    assert first.eroded == second.eroded


def test_different_glyph_names_produce_distinct_topology_seeds():
    outline = proof_fixtures()["O.counter"]
    renamed = replace(outline, name="O.counter.alt")
    settings = GenerationSettings(project_seed="family", complexity=50)
    first = generate_pair(outline, settings)
    second = generate_pair(renamed, settings)
    assert first.effective_seed != second.effective_seed
    assert [fragment.identifier for fragment in first.fragments] != [
        fragment.identifier for fragment in second.fragments
    ]


def test_fragment_and_point_identity_is_matched_without_transformed_sorting():
    result = generate_pair(proof_fixtures()["H.overlap"], GenerationSettings(complexity=75))
    assert [contour.identifier for contour in result.intact.contours] == [
        contour.identifier for contour in result.eroded.contours
    ]
    assert [contour.fragment_id for contour in result.intact.contours] == [
        contour.fragment_id for contour in result.eroded.contours
    ]
    assert [contour.point_ids for contour in result.intact.contours] == [
        contour.point_ids for contour in result.eroded.contours
    ]


def test_motion_never_scales_to_or_through_zero():
    result = generate_pair(proof_fixtures()["disconnected"], GenerationSettings(complexity=90))
    assert result.fragments
    assert all(0.78 <= fragment.scale <= 1.0 for fragment in result.fragments)
    assert not any(finding.level == "hard_error" for finding in result.validation.findings)


def test_architectural_motion_keeps_a_core_and_bounds_downward_baseline_crossing():
    settings = GenerationSettings(
        project_seed="architectural-motion",
        complexity=90,
        erosion_amount=1.0,
        movement_direction_degrees=-90.0,
        movement_spread_degrees=0.0,
        maximum_downward_drift_em=0.02,
        maximum_baseline_crossing_fraction=0.12,
    )
    result = generate_pair(proof_fixtures()["H.overlap"], settings)
    largest = max(result.fragments, key=lambda fragment: fragment.area)
    smaller = [fragment for fragment in result.fragments if fragment is not largest]
    assert math.hypot(*largest.translation) < max(
        math.hypot(*fragment.translation) for fragment in smaller
    )
    assert all(fragment.translation[1] >= -20.0 for fragment in result.fragments)
    newly_crossing = 0
    for fragment in result.fragments:
        if fragment.bounds[1] < -1e-7:
            continue
        eroded_points = [
            point
            for contour in result.eroded.contours
            if contour.fragment_id == fragment.identifier
            for point in contour.points
        ]
        newly_crossing += min(y for _, y in eroded_points) < -1e-7
    assert newly_crossing <= math.floor(
        len(result.fragments) * settings.maximum_baseline_crossing_fraction
    )
    assert result.validation.compatible


def test_fragment_size_multipliers_change_motion_without_changing_topology():
    outline = proof_fixtures()["O.curve"]
    topology = generate_pair(
        outline,
        GenerationSettings(project_seed="size-multipliers", complexity=90),
    )
    frozen = regenerate_motion_from_topology(
        topology,
        GenerationSettings(
            project_seed="size-multipliers",
            complexity=90,
            large_fragment_movement_multiplier=0.0,
            medium_fragment_movement_multiplier=0.0,
            small_fragment_movement_multiplier=0.0,
        ),
        units_per_em=outline.units_per_em,
        motion_algorithm_version=MOTION_ALGORITHM_VERSION,
    )
    assert frozen.intact == topology.intact
    assert [fragment.identifier for fragment in frozen.fragments] == [
        fragment.identifier for fragment in topology.fragments
    ]
    assert all(fragment.translation == (0.0, 0.0) for fragment in frozen.fragments)
    assert all(fragment.rotation_degrees == 0.0 for fragment in frozen.fragments)
    assert all(fragment.scale == 1.0 for fragment in frozen.fragments)
    assert frozen.validation.compatible


def test_motion_algorithm_versions_are_deterministic_and_distinct():
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(project_seed="motion-version", complexity=75)
    old = generate_pair(
        outline,
        settings,
        motion_algorithm_version=MOTION_ALGORITHM_V1,
    )
    new = generate_pair(
        outline,
        settings,
        motion_algorithm_version=MOTION_ALGORITHM_VERSION,
    )
    assert old.intact == new.intact
    assert old.eroded != new.eroded
    assert generate_pair(
        outline,
        settings,
        motion_algorithm_version=MOTION_ALGORITHM_VERSION,
    ).eroded == new.eroded


def test_objective_interpolation_risk_is_blocking():
    point_ids = ("p0", "p1", "p2", "p3")
    intact_contour = MasterContour(
        "c0", "f0", 0, False,
        ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
        point_ids,
    )
    collapsed_contour = replace(
        intact_contour,
        points=((0.0, 0.0), (100.0, 0.0), (100.0, 0.0), (0.0, 0.0)),
    )
    intact = MasterGlyph("collapse", 200.0, (), (intact_contour,))
    eroded = MasterGlyph("collapse", 200.0, (), (collapsed_contour,))
    report = validate_pair(
        source_silhouette=master_contours_to_union(intact.contours),
        intact=intact,
        eroded=eroded,
        units_per_em=1000,
        minimum_area=1.0,
    )
    assert any(finding.level == "interpolation_risk" for finding in report.findings)
    assert not report.compatible


def test_fragments_respect_the_profile_minimum_area():
    result = generate_pair(proof_fixtures()["O.curve"], GenerationSettings(complexity=90))
    assert all(fragment.area >= result.profile.minimum_area for fragment in result.fragments)


def test_complexity_samples_are_deterministic_and_increase_actual_detail():
    outline = proof_fixtures()["O.curve"]
    values = (10, 25, 50, 75, 90)
    first_counts = [len(generate_pair(outline, GenerationSettings(complexity=value)).fragments) for value in values]
    second_counts = [len(generate_pair(outline, GenerationSettings(complexity=value)).fragments) for value in values]
    assert first_counts == second_counts
    assert first_counts == sorted(first_counts)
    assert first_counts[0] < first_counts[-1]


def test_component_failure_produces_no_result_pair():
    with pytest.raises(UnsupportedOutlineError):
        generate_pair(component_fixture(), GenerationSettings())


def test_reference_fixture_stays_within_stage1_performance_budget():
    start = perf_counter()
    result = generate_pair(proof_fixtures()["O.curve"], GenerationSettings(complexity=90))
    elapsed = perf_counter() - start
    assert result.validation.compatible
    assert elapsed < 1.0, f"reference generation took {elapsed:.3f}s"


def test_branching_mesh_is_deterministic_and_contains_wandering_multisegment_cracks():
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(project_seed="mesh-contract", complexity=75)
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    _, silhouette, _ = normalize_outline(outline, tolerance)
    profile = complexity_profile(75, area=silhouette.area, units_per_em=outline.units_per_em)
    seed = derive_effective_seed(settings, outline.name)
    first = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    second = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    assert [line.wkb for line in first] == [line.wkb for line in second]
    assert len(first) >= 3
    assert all(len(line.coords) >= 3 for line in first)
    segment_directions = set()
    for line in first:
        coordinates = list(line.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            segment_directions.add(round(math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])), 2))
    assert len(segment_directions) > len(first)


def test_rough_profile_preserves_macro_endpoints_and_shared_junctions():
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(project_seed="edge-contract", complexity=75)
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    _, silhouette, _ = normalize_outline(outline, tolerance)
    profile = complexity_profile(75, area=silhouette.area, units_per_em=outline.units_per_em)
    seed = derive_effective_seed(settings, outline.name)
    macro = generate_macro_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    rough = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    assert len(macro) == len(rough)
    assert sum(len(line.coords) for line in rough) > sum(len(line.coords) for line in macro) * 2
    assert all(line.is_simple for line in rough)
    parameters = edge_profile_parameters(75, outline.units_per_em)
    assert min(
        Point(first).distance(Point(second))
        for line in rough
        for first, second in zip(line.coords, list(line.coords)[1:])
    ) >= parameters.minimum_segment_length
    for first_index, first in enumerate(macro):
        for second_index in range(first_index):
            assert (first.distance(macro[second_index]) <= 1e-6) == (
                rough[first_index].distance(rough[second_index]) <= 1e-6
            )
    for endpoint in (Point(coordinate) for line in macro for coordinate in (line.coords[0], line.coords[-1])):
        for index, macro_line in enumerate(macro):
            if endpoint.distance(macro_line) <= 1e-6:
                assert endpoint.distance(rough[index]) <= 1e-7
    for macro_line, rough_line in zip(macro, rough):
        assert all(
            Point(coordinate).distance(rough_line) <= 1e-7
            for coordinate in macro_line.coords
        )


def test_edge_profile_parameters_are_bounded_and_rock_detail_increases_non_linearly():
    low = edge_profile_parameters(0, 1000)
    middle = edge_profile_parameters(50, 1000)
    high = edge_profile_parameters(100, 1000)
    assert 8 <= low.edge_subdivision_density < middle.edge_subdivision_density < high.edge_subdivision_density <= 38
    assert 1 <= low.lateral_deviation_amplitude < high.lateral_deviation_amplitude <= 14
    assert 0.15 <= low.segment_length_variation <= high.segment_length_variation <= 0.5
    assert 0 < low.sharp_corner_probability < high.sharp_corner_probability < 0.2
    assert 0 < low.local_notch_probability < high.local_notch_probability < 0.1
    assert 0 < high.simplification_threshold < low.simplification_threshold < 3
    assert 7 <= high.minimum_segment_length < low.minimum_segment_length <= 14


def test_rock_edge_detail_changes_only_micro_mesh_for_fixed_macro_seed():
    outline = proof_fixtures()["O.curve"]
    base = GenerationSettings(
        project_seed="independent-rock-detail",
        complexity=75,
        rock_edge_detail=0,
    )
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    _, silhouette, _ = normalize_outline(outline, tolerance)
    profile = complexity_profile(75, area=silhouette.area, units_per_em=outline.units_per_em)
    seed = derive_effective_seed(base, outline.name)
    macro = generate_macro_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    low = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em, 0)
    high = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em, 100)

    assert derive_effective_seed(replace(base, rock_edge_detail=100), outline.name) == seed
    assert len(low) == len(high) == len(macro)
    assert [line.coords[0] for line in low] == [line.coords[0] for line in high]
    assert [line.coords[-1] for line in low] == [line.coords[-1] for line in high]
    assert sum(len(line.coords) for line in high) > sum(len(line.coords) for line in low)
    assert [line.wkb for line in high] != [line.wkb for line in low]


@pytest.mark.parametrize("detail", (0, 25, 50, 75, 100))
def test_rock_edge_detail_samples_are_deterministic_compatible_and_reconstruct(detail):
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(
        project_seed="rock-detail-samples",
        complexity=75,
        rock_edge_detail=detail,
    )
    first = generate_pair(outline, settings)
    second = generate_pair(outline, settings)

    assert first.rock_edge_detail == detail
    assert first.fragments == second.fragments
    assert first.intact == second.intact
    assert first.validation.compatible
    assert first.validation.reconstruction.normalized_symmetric_difference <= 1e-8


def test_rock_edge_detail_increases_points_while_fragment_count_stays_broadly_stable():
    outline = proof_fixtures()["O.curve"]
    results = [
        generate_pair(
            outline,
            GenerationSettings(
                project_seed="rock-detail-samples",
                complexity=75,
                rock_edge_detail=detail,
            ),
        )
        for detail in (0, 25, 50, 75, 100)
    ]
    fragment_counts = [len(result.fragments) for result in results]
    point_counts = [
        sum(len(contour.points) for contour in result.intact.contours)
        for result in results
    ]

    assert len(set(fragment_counts)) == 1
    assert point_counts == sorted(point_counts)
    assert point_counts[-1] >= point_counts[0] * 1.35


def test_rock_edge_detail_preserves_fragment_identity_metrics_adjacency_and_motion():
    outline = proof_fixtures()["O.curve"]
    results = [
        generate_pair(
            outline,
            GenerationSettings(
                project_seed="rock-detail-stable",
                complexity=75,
                rock_edge_detail=detail,
            ),
        )
        for detail in (0, 50, 100)
    ]

    def identity_and_metrics(result):
        return tuple(
            (
                fragment.identifier,
                fragment.area,
                fragment.centroid,
                fragment.bounds,
                fragment.transform_origin,
            )
            for fragment in result.fragments
        )

    def motion(result):
        return tuple(
            (
                fragment.translation,
                fragment.rotation_degrees,
                fragment.scale,
            )
            for fragment in result.fragments
        )

    def adjacency(result):
        geometries = [
            master_contours_to_union(fragment.intact_contours)
            for fragment in result.fragments
        ]
        return frozenset(
            (second, first)
            for first in range(len(geometries))
            for second in range(first)
            if geometries[first].boundary.intersection(
                geometries[second].boundary
            ).length > 1e-7
        )

    assert all(
        identity_and_metrics(result) == identity_and_metrics(results[0])
        for result in results[1:]
    )
    assert all(motion(result) == motion(results[0]) for result in results[1:])
    assert all(adjacency(result) == adjacency(results[0]) for result in results[1:])
    assert len({result.intact for result in results}) == 3
    assert [
        sum(len(contour.points) for contour in result.intact.contours)
        for result in results
    ] == sorted(
        sum(len(contour.points) for contour in result.intact.contours)
        for result in results
    )
    assert all(result.validation.compatible for result in results)


@pytest.mark.parametrize("value", (-1, 101, 50.5, True))
def test_rock_edge_detail_rejects_values_outside_integer_slider_domain(value):
    with pytest.raises(ValueError, match="rock_edge_detail"):
        GenerationSettings(rock_edge_detail=value)


def test_boundary_provenance_has_no_unexplained_clipping_nodes():
    outline = proof_fixtures()["O.curve"]
    settings = GenerationSettings(project_seed="mesh-provenance", complexity=75)
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    _, silhouette, _ = normalize_outline(outline, tolerance)
    profile = complexity_profile(75, area=silhouette.area, units_per_em=outline.units_per_em)
    seed = derive_effective_seed(settings, outline.name)
    mesh = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
    pieces = generate_topology(silhouette, profile, seed, outline.units_per_em)
    provenance = boundary_point_provenance(
        silhouette,
        pieces,
        mesh,
        distance_tolerance=max(tolerance * 0.01, 1e-6),
    )
    assert provenance["requiredCrackBoundaryPoints"]
    assert provenance["baselineFlatteningBoundaryPoints"]
    assert len(provenance["clippingArtifactBoundaryPoints"]) <= 8
