from __future__ import annotations

from pathlib import Path

from fracturize import GenerationSettings, generate_pair
from test_support.fixtures import proof_fixtures
from fracturize.geometry import flatten_outline, master_contours_to_union, visible_filled_union
from fracturize.ufo import read_master, write_temporary_pair
from fracturize.validation import validate_pair


def test_temporary_ufo_pair_serializes_and_reopens_with_identity(tmp_path: Path):
    result = generate_pair(proof_fixtures()["O.curve"], GenerationSettings(complexity=50))
    intact_path = tmp_path / "Proof-Intact.ufo"
    eroded_path = tmp_path / "Proof-Eroded.ufo"
    write_temporary_pair(result, intact_path, eroded_path)

    intact = read_master(intact_path, result.glyph_name)
    eroded = read_master(eroded_path, result.glyph_name)
    assert intact.width == eroded.width == result.intact.width
    assert [contour.identifier for contour in intact.contours] == [
        contour.identifier for contour in eroded.contours
    ]
    assert [contour.point_ids for contour in intact.contours] == [
        contour.point_ids for contour in eroded.contours
    ]
    assert [contour.fragment_id for contour in intact.contours] == [
        contour.fragment_id for contour in eroded.contours
    ]
    assert master_contours_to_union(intact.contours).symmetric_difference(
        master_contours_to_union(result.intact.contours)
    ).area <= 1e-8
    source = visible_filled_union(
        flatten_outline(proof_fixtures()["O.curve"], result.flattening_tolerance)
    )
    reopened_report = validate_pair(
        source_silhouette=source,
        intact=intact,
        eroded=eroded,
        units_per_em=1000,
        minimum_area=result.profile.minimum_area,
    )
    assert reopened_report.compatible


def test_temporary_ufo_output_contains_only_line_points(tmp_path: Path):
    result = generate_pair(proof_fixtures()["O.curve"], GenerationSettings(complexity=25))
    intact_path = tmp_path / "Intact.ufo"
    eroded_path = tmp_path / "Eroded.ufo"
    write_temporary_pair(result, intact_path, eroded_path)

    from defcon import Font

    font = Font(intact_path)
    assert all(point.segmentType == "line" for contour in font[result.glyph_name] for point in contour)
    font.close()
