from __future__ import annotations

import hashlib
from pathlib import Path
from collections import Counter

from defcon import Font
import pytest

from fracturize.core import OUTLINE_RECONSTRUCTION_VERSION, generate_pair
from fracturize.geometry import (
    UnsupportedOutlineError,
    flatten_outline,
    master_contours_to_union,
    visible_filled_union,
)
from fracturize.input_ufo import defcon_glyph_to_outline
from fracturize.model import CubicSegment, GenerationSettings, LineSegment
from fracturize.topology import topology_from_dict, topology_to_dict
from fracturize.ufo import read_master, write_temporary_pair
from test_support.fixtures import component_fixture, proof_fixtures


SETTINGS = GenerationSettings(
    project_seed="cubic-phase3",
    complexity=30,
    rock_edge_detail=0,
)
REGRESSION_UFO = Path(__file__).parent / "fixtures" / "FracturizeRegression.ufo"


def _tree_digest(path):
    digest = hashlib.sha256()
    for item in sorted(file for file in path.rglob("*") if file.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def test_production_hybrid_preserves_source_cubics_counter_and_compatibility():
    before = _tree_digest(REGRESSION_UFO)
    font = Font(REGRESSION_UFO)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    result = generate_pair(outline, SETTINGS)

    segments = [segment for contour in result.intact.contours for segment in contour.segments]
    assert result.outline_reconstruction_version == OUTLINE_RECONSTRUCTION_VERSION
    assert sum(isinstance(segment, CubicSegment) for segment in segments) > 8
    assert any(isinstance(segment, LineSegment) for segment in segments)
    assert result.validation.compatible

    source = visible_filled_union(flatten_outline(outline, 0.001))
    intact = master_contours_to_union(result.intact.contours, tolerance=0.001)
    assert source.symmetric_difference(intact).area / source.area <= 3e-6
    assert source.boundary.hausdorff_distance(intact.boundary) <= 0.001
    assert len(intact.interiors) == 1
    assert _tree_digest(REGRESSION_UFO) == before

    original_nodes = {
        tuple(round(value, 7) for value in segment.end)
        for contour in outline.contours
        for segment in contour.segments
    }
    cubic_nodes = {
        tuple(round(value, 7) for value in point)
        for segment in segments
        if isinstance(segment, CubicSegment)
        for point in (segment.start, segment.end)
    }
    # Exact subdivision adds a bounded set of curve nodes, rather than the
    # dense flattening points used by the previous polygonal exterior.
    assert 0 < len(cubic_nodes - original_nodes) < 32

    internal_uses = Counter(
        tuple(
            sorted(
                tuple(round(value, 7) for value in point)
                for point in (segment.start, segment.end)
            )
        )
        for segment in segments
        if isinstance(segment, LineSegment)
    )
    assert internal_uses
    assert set(internal_uses.values()) == {2}


def test_hybrid_segment_types_survive_ufo_save_and_reopen(tmp_path):
    font = Font(REGRESSION_UFO)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    result = generate_pair(outline, SETTINGS)
    intact_path = tmp_path / "Hybrid-Intact.ufo"
    eroded_path = tmp_path / "Hybrid-Eroded.ufo"
    write_temporary_pair(result, intact_path, eroded_path)

    reopened = read_master(intact_path, "O")
    expected = sorted(
        (sum(isinstance(segment, CubicSegment) for segment in contour.segments),
         sum(isinstance(segment, LineSegment) for segment in contour.segments))
        for contour in result.intact.contours
    )
    actual = sorted(
        (sum(isinstance(segment, CubicSegment) for segment in contour.segments),
         sum(isinstance(segment, LineSegment) for segment in contour.segments))
        for contour in reopened.contours
    )
    assert actual == expected
    assert master_contours_to_union(reopened.contours).symmetric_difference(
        master_contours_to_union(result.intact.contours)
    ).area <= 1e-8


def test_topology_v3_roundtrip_retains_exact_segments():
    font = Font(REGRESSION_UFO)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    result = generate_pair(outline, SETTINGS)
    data = topology_to_dict(result, units_per_em=1000)
    restored, units_per_em = topology_from_dict(data)
    assert data["formatVersion"] == 3
    assert units_per_em == 1000
    assert restored.outline_reconstruction_version == OUTLINE_RECONSTRUCTION_VERSION
    assert restored.intact.contours == result.intact.contours


@pytest.mark.parametrize(
    "outline, reason",
    (
        (component_fixture(), "components"),
        (proof_fixtures()["H.overlap"], "overlapping"),
    ),
)
def test_unsupported_constructions_are_rejected_without_polygonal_fallback(outline, reason):
    with pytest.raises(UnsupportedOutlineError, match=reason):
        generate_pair(outline, SETTINGS)
