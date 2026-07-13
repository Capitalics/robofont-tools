from __future__ import annotations

import pytest

from fracturize.core import complexity_profile, derive_effective_seed
from fracturize import GenerationSettings, generate_pair
from fracturize.fixtures import component_fixture, line_contour, open_contour_fixture, proof_fixtures
from fracturize.geometry import (
    UnsupportedOutlineError,
    adaptive_flattening_tolerance,
    flatten_outline,
    visible_filled_union,
)
from fracturize.model import GenerationSettings, GlyphOutline


def test_adaptive_flattening_tolerance_is_upm_relative_and_clamped():
    assert adaptive_flattening_tolerance(1000) == 0.5
    assert adaptive_flattening_tolerance(200) == 0.25
    assert adaptive_flattening_tolerance(4000) == 1.0


def test_curve_fixture_is_adaptively_flattened_to_many_line_points():
    outline = proof_fixtures()["O.curve"]
    rings = flatten_outline(outline, adaptive_flattening_tolerance(outline.units_per_em))
    assert len(rings) == 2
    assert len(rings[0]) > 80
    assert len(rings[1]) > 40


def test_nonzero_normalization_unions_overlapping_contours():
    outline = proof_fixtures()["H.overlap"]
    geometry = visible_filled_union(flatten_outline(outline, 0.5))
    assert geometry.area == pytest.approx(215600.0)


def test_nonzero_normalization_preserves_counter():
    outline = proof_fixtures()["O.counter"]
    geometry = visible_filled_union(flatten_outline(outline, 0.5))
    assert geometry.area == pytest.approx(276000.0)
    assert not geometry.contains(geometry.representative_point().__class__(350, 400))


def test_nonzero_normalization_preserves_nested_island():
    outline = proof_fixtures()["nested"]
    geometry = visible_filled_union(flatten_outline(outline, 0.5))
    from shapely.geometry import Point

    assert geometry.contains(Point(100, 100))
    assert not geometry.contains(Point(220, 220))
    assert geometry.contains(Point(350, 400))


def test_components_are_explicitly_rejected():
    with pytest.raises(UnsupportedOutlineError, match="components are unsupported"):
        flatten_outline(component_fixture(), 0.5)


def test_open_contours_are_explicitly_rejected():
    with pytest.raises(UnsupportedOutlineError, match="is open"):
        flatten_outline(open_contour_fixture(), 0.5)


def test_empty_outline_is_rejected():
    with pytest.raises(UnsupportedOutlineError, match="no contours"):
        flatten_outline(GlyphOutline("empty", 500, 1000, ()), 0.5)


def test_ordinary_bowtie_self_intersection_is_not_silently_repaired():
    outline = GlyphOutline(
        "malformed.bowtie",
        500,
        1000,
        (line_contour(((100, 100), (400, 500), (100, 500), (400, 100))),),
    )
    with pytest.raises(UnsupportedOutlineError, match="no multiply-wound overlap region"):
        generate_pair(outline, GenerationSettings())


def test_seed_derivation_is_stable_and_glyph_specific():
    settings = GenerationSettings(project_seed="test", complexity=50)
    assert derive_effective_seed(settings, "A") == derive_effective_seed(settings, "A")
    assert derive_effective_seed(settings, "A") != derive_effective_seed(settings, "B")


def test_complexity_profile_changes_a_parameter_bundle_monotonically():
    profiles = [complexity_profile(value, area=300000, units_per_em=1000) for value in (10, 25, 50, 75, 90)]
    assert [profile.target_fragments for profile in profiles] == sorted(
        profile.target_fragments for profile in profiles
    )
    assert [profile.primary_split_count for profile in profiles] == sorted(
        profile.primary_split_count for profile in profiles
    )
    assert [profile.detail_depth for profile in profiles] == sorted(
        profile.detail_depth for profile in profiles
    )
    assert [profile.minimum_area for profile in profiles] == sorted(
        (profile.minimum_area for profile in profiles), reverse=True
    )
    assert profiles[0].chip_probability < profiles[-1].chip_probability
    assert profiles[0].edge_irregularity < profiles[-1].edge_irregularity


def test_complexity_profile_is_bounded_for_extreme_values():
    low = complexity_profile(0, area=10_000_000, units_per_em=1000)
    high = complexity_profile(100, area=10_000_000, units_per_em=1000)
    assert low.target_fragments == 1
    assert high.target_fragments <= 28
    assert high.minimum_area > 0
    with pytest.raises(ValueError):
        complexity_profile(101, area=300000, units_per_em=1000)


def test_representative_complexities_produce_meaningfully_different_density():
    outline = proof_fixtures()["O.curve"]
    results = [
        generate_pair(
            outline,
            GenerationSettings(project_seed="complexity-density", complexity=value),
        )
        for value in (10, 30, 50, 70, 90)
    ]
    counts = [len(result.fragments) for result in results]
    assert counts == sorted(counts)
    assert counts[-1] - counts[0] >= 8
    assert len({result.effective_seed for result in results}) == len(results)

    repeated = generate_pair(
        outline,
        GenerationSettings(project_seed="complexity-density", complexity=70),
    )
    assert repeated.intact == results[3].intact
    assert [fragment.identifier for fragment in repeated.fragments] == [
        fragment.identifier for fragment in results[3].fragments
    ]
