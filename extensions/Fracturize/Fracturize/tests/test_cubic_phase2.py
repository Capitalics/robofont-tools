from __future__ import annotations

import hashlib
from pathlib import Path

from defcon import Font
import pytest
from shapely.geometry import Polygon

from fracturize.core import (
    complexity_profile,
    derive_effective_seed,
    generate_clean_macro_topology,
    generate_macro_crack_mesh,
    generate_pair,
)
from fracturize.geometry import adaptive_flattening_tolerance, normalize_outline
from fracturize.input_ufo import defcon_glyph_to_outline
from fracturize.model import CubicSegment, GenerationSettings, LineSegment
from test_support.cubic_intersections import cubic_point
from test_support.hybrid_reconstruction import (
    hybrid_glyph_geometry,
    interpolate_hybrid_glyph,
    reconstruct_hybrid_glyph,
    shared_internal_edge_uses,
    structural_signature,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "FracturizeRegression.ufo"
SETTINGS = GenerationSettings(
    project_seed="cubic-phase2",
    complexity=30,
    rock_edge_detail=0,
)


def _tree_digest(path):
    digest = hashlib.sha256()
    for item in sorted(file for file in path.rglob("*") if file.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _sample_source_contour(contour, samples=1024):
    points = []
    for segment in contour.segments:
        if isinstance(segment, CubicSegment):
            points.extend(cubic_point(segment, index / samples) for index in range(samples))
        else:
            points.append(segment.start)
    return points


@pytest.fixture(scope="module")
def phase2_proof():
    before = _tree_digest(FIXTURE)
    font = Font(FIXTURE)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    tolerance = adaptive_flattening_tolerance(outline.units_per_em)
    _, silhouette, _ = normalize_outline(outline, tolerance)
    profile = complexity_profile(
        SETTINGS.complexity,
        area=silhouette.area,
        units_per_em=outline.units_per_em,
    )
    seed = derive_effective_seed(SETTINGS, outline.name)
    crack_lines = generate_macro_crack_mesh(
        silhouette, profile, seed, outline.units_per_em
    )
    faces = generate_clean_macro_topology(
        silhouette, profile, seed, outline.units_per_em
    )
    guide = generate_pair(
        outline,
        SETTINGS,
        topology_generator=generate_clean_macro_topology,
    )
    proof = reconstruct_hybrid_glyph(
        outline,
        faces,
        crack_lines,
        guide.fragments,
        flattening_tolerance=tolerance,
    )
    assert _tree_digest(FIXTURE) == before
    return outline, guide, proof


def test_phase2_uses_several_macro_cracks_and_more_than_two_fragments(phase2_proof):
    _, guide, proof = phase2_proof
    assert len(proof.crack_lines) == 7
    assert len(proof.intact.fragments) == len(guide.fragments) == 5
    assert [fragment.identifier for fragment in proof.intact.fragments] == [
        fragment.identifier for fragment in guide.fragments
    ]
    assert [fragment.translation for fragment in proof.intact.fragments] == [
        fragment.translation for fragment in guide.fragments
    ]


def test_phase2_classifies_exact_cubic_exterior_and_generated_internal_lines(phase2_proof):
    _, _, proof = phase2_proof
    segments = [
        segment
        for fragment in proof.intact.fragments
        for contour in fragment.contours
        for segment in contour.segments
    ]
    exterior = [segment for segment in segments if segment.kind == "exterior"]
    internal = [segment for segment in segments if segment.kind == "internal"]
    assert len(exterior) == 16
    assert all(isinstance(segment.geometry, CubicSegment) for segment in exterior)
    assert all(segment.source_t_range is not None for segment in exterior)
    assert all(segment.source_t_range[0] < segment.source_t_range[1] for segment in exterior)
    assert all(isinstance(segment.geometry, LineSegment) for segment in internal)


def test_phase2_adds_only_fracture_intersection_nodes_to_source_curves(phase2_proof):
    outline, _, proof = phase2_proof
    original_nodes = {
        (round(segment.end[0], 8), round(segment.end[1], 8))
        for contour in outline.contours
        for segment in contour.segments
    }
    exterior_nodes = {
        (round(segment.geometry.end[0], 8), round(segment.geometry.end[1], 8))
        for fragment in proof.intact.fragments
        for contour in fragment.contours
        for segment in contour.segments
        if segment.kind == "exterior"
    }
    introduced = exterior_nodes - original_nodes
    expected = {
        (round(point[0], 8), round(point[1], 8))
        for point in proof.new_exterior_nodes
    }
    assert introduced == expected
    assert len(introduced) == 8

    ranges = {}
    for fragment in proof.intact.fragments:
        for contour in fragment.contours:
            for segment in contour.segments:
                if segment.kind == "exterior":
                    key = (segment.source_contour_index, segment.source_segment_index)
                    ranges.setdefault(key, []).append(segment.source_t_range)
    assert len(ranges) == 8
    for source_ranges in ranges.values():
        source_ranges.sort()
        assert source_ranges[0][0] == 0.0
        assert source_ranges[-1][1] == 1.0
        assert all(
            first[1] == second[0]
            for first, second in zip(source_ranges, source_ranges[1:])
        )


def test_phase2_shared_internal_segments_are_reused_exactly_in_reverse(phase2_proof):
    _, _, proof = phase2_proof
    uses = shared_internal_edge_uses(proof.intact)
    assert len(proof.shared_edge_ids) == 6
    assert len(uses) == 12
    for records in uses.values():
        assert len(records) == 2
        first = records[0][1]
        second = records[1][1]
        assert first.start == second.end
        assert first.end == second.start


def test_phase2_reconstructs_counter_and_produces_compatible_masters(phase2_proof):
    outline, _, proof = phase2_proof
    source = Polygon(
        _sample_source_contour(outline.contours[0]),
        [_sample_source_contour(outline.contours[1])],
    )
    intact = hybrid_glyph_geometry(proof.intact, samples_per_cubic=1024)
    normalized_difference = source.symmetric_difference(intact).area / source.area
    hausdorff = source.boundary.hausdorff_distance(intact.boundary)
    assert intact.geom_type == "Polygon"
    assert len(intact.interiors) == 1
    assert normalized_difference <= 1e-6
    assert hausdorff <= 1e-3
    assert structural_signature(proof.intact) == structural_signature(proof.eroded)

    for factor in (0.0, 0.25, 0.5, 0.75, 1.0):
        interpolated = interpolate_hybrid_glyph(proof.intact, proof.eroded, factor)
        geometry = hybrid_glyph_geometry(interpolated, samples_per_cubic=128)
        assert geometry.is_valid
        assert geometry.area > 0
