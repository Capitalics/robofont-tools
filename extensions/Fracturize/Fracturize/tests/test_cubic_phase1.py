from __future__ import annotations

import math
from pathlib import Path

from defcon import Font

from fracturize.input_ufo import defcon_glyph_to_outline
from fracturize.model import CubicSegment, LineSegment, SourceContour
from test_support.cubic_intersections import (
    cubic_point,
    intersect_contour_with_line,
    intersect_cubic_with_line,
    maximum_reconstruction_error,
    split_contour_at_intersections,
    split_cubic,
    split_cubic_many,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "FracturizeRegression.ufo"


def _signed_area(points):
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:] + points[:1])
    )


def _sample_segments(segments, samples_per_cubic=100):
    points = []
    for segment in segments:
        if isinstance(segment, CubicSegment):
            points.extend(
                cubic_point(segment, index / samples_per_cubic)
                for index in range(samples_per_cubic)
            )
        else:
            points.append(segment.start)
    return points


def test_de_casteljau_split_has_exact_expected_control_points():
    segment = CubicSegment((0, 0), (0, 2), (2, 2), (2, 0))
    left, right = split_cubic(segment, 0.5)
    assert left == CubicSegment((0, 0), (0, 1), (0.5, 1.5), (1, 1.5))
    assert right == CubicSegment((1, 1.5), (1.5, 1.5), (2, 1), (2, 0))


def test_two_intersections_on_one_cubic_are_refined_and_parameter_ordered():
    segment = CubicSegment((0, 0), (100, 300), (200, -300), (300, 0))
    line = LineSegment((-50, 50), (350, 50))
    intersections = intersect_cubic_with_line(
        segment,
        line,
        proxy_tolerance=0.2,
        refinement_tolerance=1e-10,
    )
    assert len(intersections) == 2
    assert 0 < intersections[0].t < intersections[1].t < 1
    assert all(abs(item.point[1] - 50) <= 1e-10 for item in intersections)
    assert all(item.refinement_error <= 1e-10 for item in intersections)
    assert any(abs(item.t - item.proxy_t) > 1e-5 for item in intersections)


def test_multiple_split_pieces_reproduce_original_cubic():
    segment = CubicSegment((0, 0), (100, 300), (200, -300), (300, 0))
    line = LineSegment((-50, 50), (350, 50))
    intersections = intersect_cubic_with_line(segment, line, proxy_tolerance=0.2)
    parameters = [item.t for item in intersections]
    pieces = split_cubic_many(segment, parameters)
    assert len(pieces) == 3
    assert all(isinstance(piece, CubicSegment) for piece in pieces)
    assert maximum_reconstruction_error(segment, pieces, parameters) <= 1e-10


def test_split_contour_preserves_source_direction_and_continuity():
    cubic = CubicSegment((0, 0), (100, 300), (200, -300), (300, 0))
    contour = SourceContour((cubic, LineSegment((300, 0), (0, 0))))
    line = LineSegment((-50, 50), (350, 50))
    intersections = intersect_contour_with_line(contour, line, proxy_tolerance=0.2)
    pieces = split_contour_at_intersections(contour, intersections)
    assert pieces[0].start == contour.segments[0].start
    assert pieces[-1].end == contour.segments[-1].end
    assert all(first.end == second.start for first, second in zip(pieces, pieces[1:]))
    original_area = _signed_area(_sample_segments(contour.segments))
    split_area = _signed_area(_sample_segments(pieces))
    assert math.copysign(1, original_area) == math.copysign(1, split_area)


def test_regression_o_maps_four_intersections_to_original_cubic_segments_only():
    font = Font(FIXTURE)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    fracture = LineSegment((0, 420), (690, 420))
    intersections = tuple(
        item
        for contour in outline.contours
        for item in intersect_contour_with_line(
            contour,
            fracture,
            proxy_tolerance=0.1,
            refinement_tolerance=1e-10,
        )
    )
    assert len(intersections) == 4
    assert all(item.refinement_error <= 1e-10 for item in intersections)
    assert all(abs(item.point[1] - 420) <= 1e-10 for item in intersections)

    split_piece_count = 0
    introduced_points = []
    for contour in outline.contours:
        contour_intersections = intersect_contour_with_line(
            contour,
            fracture,
            proxy_tolerance=0.1,
        )
        pieces = split_contour_at_intersections(contour, contour_intersections)
        split_piece_count += len(pieces)
        assert all(isinstance(piece, CubicSegment) for piece in pieces)
        original_nodes = {segment.end for segment in contour.segments}
        introduced_points.extend(
            piece.end for piece in pieces if piece.end not in original_nodes
        )
    assert split_piece_count == 12  # 8 source cubics plus 4 intersection splits.
    assert len(introduced_points) == 4
    assert all(
        any(math.dist(point, intersection.point) <= 1e-9 for intersection in intersections)
        for point in introduced_points
    )
