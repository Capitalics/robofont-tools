from __future__ import annotations

"""Generate the standalone Phase 1 cubic-intersection proof artifact."""

import hashlib
import json
import math
from pathlib import Path

from defcon import Font
from shapely.geometry import Polygon
from shapely.ops import unary_union

from fracturize import GenerationSettings, generate_pair
from fracturize.input_ufo import defcon_glyph_to_outline
from fracturize.model import CubicSegment, LineSegment
from test_support.cubic_intersections import (
    cubic_point,
    intersect_contour_with_line,
    maximum_reconstruction_error,
    split_contour_at_intersections,
    split_cubic_many,
)


PROXY_TOLERANCE = 0.1
REFINEMENT_TOLERANCE = 1e-10
CURVE_RECONSTRUCTION_TOLERANCE = 1e-10
SILHOUETTE_AREA_TOLERANCE = 1e-6
SILHOUETTE_HAUSDORFF_TOLERANCE = 1e-3
SILHOUETTE_SAMPLES_PER_CUBIC = 1024


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _point_matches(first, second, tolerance=1e-8):
    return math.dist(first, second) <= tolerance


def _two_arcs(contour, fracture):
    intersections = intersect_contour_with_line(
        contour,
        fracture,
        proxy_tolerance=PROXY_TOLERANCE,
        refinement_tolerance=REFINEMENT_TOLERANCE,
    )
    if len(intersections) != 2:
        raise RuntimeError("Phase 1 O proof expects two intersections per contour")
    pieces = split_contour_at_intersections(contour, intersections)
    indexes = [
        next(
            index
            for index, piece in enumerate(pieces)
            if _point_matches(piece.start, intersection.point)
        )
        for intersection in intersections
    ]
    first, second = indexes
    arcs = (pieces[first:second], pieces[second:] + pieces[:first])
    # For this horizontal proof cut, mean midpoint height identifies the arcs
    # without changing their original source-contour direction.
    arcs = tuple(
        sorted(
            arcs,
            key=lambda arc: sum(cubic_point(segment, 0.5)[1] for segment in arc)
            / len(arc),
            reverse=True,
        )
    )
    return intersections, arcs


def _hybrid_fragment(outer_arc, inner_arc):
    return (
        *outer_arc,
        LineSegment(outer_arc[-1].end, inner_arc[0].start),
        *inner_arc,
        LineSegment(inner_arc[-1].end, outer_arc[0].start),
    )


def _sample_segments(segments, samples_per_cubic=SILHOUETTE_SAMPLES_PER_CUBIC):
    points = []
    for segment in segments:
        if isinstance(segment, CubicSegment):
            points.extend(
                cubic_point(segment, index / samples_per_cubic)
                for index in range(samples_per_cubic)
            )
        else:
            points.append(segment.start)
    points.append(segments[-1].end)
    return points


def _source_geometry(outline):
    outer = _sample_segments(outline.contours[0].segments)
    counters = [_sample_segments(contour.segments) for contour in outline.contours[1:]]
    return Polygon(outer, counters)


def _path_for_segments(segments):
    rows = [f"M {segments[0].start[0]:.9f} {-segments[0].start[1]:.9f}"]
    for segment in segments:
        if isinstance(segment, CubicSegment):
            rows.append(
                "C "
                f"{segment.control1[0]:.9f} {-segment.control1[1]:.9f} "
                f"{segment.control2[0]:.9f} {-segment.control2[1]:.9f} "
                f"{segment.end[0]:.9f} {-segment.end[1]:.9f}"
            )
        else:
            rows.append(f"L {segment.end[0]:.9f} {-segment.end[1]:.9f}")
    rows.append("Z")
    return " ".join(rows)


def _path_for_master(master):
    rows = []
    for contour in master.contours:
        rows.append(f"M {contour.points[0][0]:.9f} {-contour.points[0][1]:.9f}")
        rows.extend(f"L {x:.9f} {-y:.9f}" for x, y in contour.points[1:])
        rows.append("Z")
    return " ".join(rows)


def _write_svg(path, outline, current, hybrid_fragments, intersections, metrics):
    source_path = " ".join(_path_for_segments(contour.segments) for contour in outline.contours)
    hybrid_paths = [_path_for_segments(fragment) for fragment in hybrid_fragments]
    current_path = _path_for_master(current.intact)
    columns = (40, 740, 1440)
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="2100" height="900" viewBox="0 0 2100 900">',
        '<rect width="100%" height="100%" fill="#f4f0e7"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#292622}.title{font-size:26px}.meta{font-size:16px;fill:#625c54}.shape{fill:#292622;fill-rule:nonzero}.fragment{fill:#292622;stroke:#cf654b;stroke-width:1.25}.fracture{stroke:#ef5b3f;stroke-width:4;fill:none}.node{fill:#2d83a8;stroke:white;stroke-width:2}</style>',
        f'<text class="title" x="{columns[0]}" y="42">Original source outline</text>',
        f'<text class="title" x="{columns[1]}" y="42">Current polygonal result</text>',
        f'<text class="title" x="{columns[2]}" y="42">Phase 1 cubic-preserving proof</text>',
        f'<text class="meta" x="{columns[0]}" y="68">8 source cubic segments</text>',
        f'<text class="meta" x="{columns[1]}" y="68">line-only fragment contours</text>',
        f'<text class="meta" x="{columns[2]}" y="68">12 exact cubic pieces; 4 new intersection nodes</text>',
        f'<g transform="translate({columns[0]},790)"><path class="shape" d="{source_path}"/></g>',
        f'<g transform="translate({columns[1]},790)"><path class="shape" d="{current_path}"/></g>',
        f'<g transform="translate({columns[2]},790)">',
    ]
    for hybrid_path in hybrid_paths:
        rows.append(f'<path class="fragment" d="{hybrid_path}"/>')
    unique_lines = {}
    for fragment in hybrid_fragments:
        for segment in fragment:
            if isinstance(segment, LineSegment):
                key = tuple(sorted((segment.start, segment.end)))
                unique_lines[key] = segment
    for segment in unique_lines.values():
        rows.append(
            f'<path class="fracture" d="M {segment.start[0]:.9f} {-segment.start[1]:.9f} '
            f'L {segment.end[0]:.9f} {-segment.end[1]:.9f}"/>'
        )
    for intersection in intersections:
        rows.append(
            f'<circle class="node" cx="{intersection.point[0]:.9f}" '
            f'cy="{-intersection.point[1]:.9f}" r="6"/>'
        )
    rows.extend(
        [
            "</g>",
            f'<text class="meta" x="{columns[2]}" y="842">max exact curve error: {metrics["maximumCurveReconstructionError"]:.3e} units</text>',
            f'<text class="meta" x="{columns[2]}" y="866">sampled silhouette difference: {metrics["normalizedSilhouetteDifference"]:.3e}</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests" / "fixtures" / "FracturizeRegression.ufo"
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    before = tree_digest(fixture)

    font = Font(fixture)
    outline = defcon_glyph_to_outline(font["O"], units_per_em=1000)
    font.close()
    fracture = LineSegment((0, 420), (690, 420))
    outer_intersections, (outer_upper, outer_lower) = _two_arcs(
        outline.contours[0], fracture
    )
    inner_intersections, (inner_upper, inner_lower) = _two_arcs(
        outline.contours[1], fracture
    )
    intersections = (*outer_intersections, *inner_intersections)
    hybrid_fragments = (
        _hybrid_fragment(outer_upper, inner_upper),
        _hybrid_fragment(outer_lower, inner_lower),
    )

    maximum_curve_error = 0.0
    for contour in outline.contours:
        contour_intersections = intersect_contour_with_line(
            contour,
            fracture,
            proxy_tolerance=PROXY_TOLERANCE,
            refinement_tolerance=REFINEMENT_TOLERANCE,
        )
        for index, segment in enumerate(contour.segments):
            parameters = [
                item.t for item in contour_intersections if item.segment_index == index
            ]
            pieces = split_cubic_many(segment, parameters)
            maximum_curve_error = max(
                maximum_curve_error,
                maximum_reconstruction_error(segment, pieces, parameters),
            )

    source_geometry = _source_geometry(outline)
    hybrid_geometry = unary_union(
        [Polygon(_sample_segments(fragment)) for fragment in hybrid_fragments]
    )
    normalized_difference = (
        source_geometry.symmetric_difference(hybrid_geometry).area / source_geometry.area
    )
    hausdorff = source_geometry.hausdorff_distance(hybrid_geometry)

    line_keys = []
    for fragment in hybrid_fragments:
        for segment in fragment:
            if isinstance(segment, LineSegment):
                line_keys.append(tuple(sorted((segment.start, segment.end))))
    complementary = len(line_keys) == 4 and all(line_keys.count(key) == 2 for key in set(line_keys))
    introduced_points = {
        (round(item.point[0], 9), round(item.point[1], 9)) for item in intersections
    }
    current = generate_pair(
        outline,
        GenerationSettings(
            project_seed="cubic-phase1-comparison",
            complexity=30,
            rock_edge_detail=35,
        ),
    )
    after = tree_digest(fixture)
    metrics = {
        "glyph": "O",
        "fractureLine": [list(fracture.start), list(fracture.end)],
        "sourceCubicSegments": 8,
        "hybridExteriorCubicPieces": sum(
            isinstance(segment, CubicSegment)
            for fragment in hybrid_fragments
            for segment in fragment
        ),
        "introducedExteriorPoints": len(introduced_points),
        "fractureIntersections": [
            {
                "segmentIndex": item.segment_index,
                "t": item.t,
                "point": list(item.point),
                "refinementError": item.refinement_error,
            }
            for item in intersections
        ],
        "generatedInternalLineInstances": len(line_keys),
        "uniqueInternalFractureEdges": len(set(line_keys)),
        "internalEdgesComplementary": complementary,
        "maximumCurveReconstructionError": maximum_curve_error,
        "normalizedSilhouetteDifference": normalized_difference,
        "silhouetteHausdorffDistance": hausdorff,
        "sourceUnmodified": before == after,
        "currentPolygonalPointCount": sum(
            len(contour.points) for contour in current.intact.contours
        ),
        "tolerances": {
            "intersectionRefinement": REFINEMENT_TOLERANCE,
            "curveReconstruction": CURVE_RECONSTRUCTION_TOLERANCE,
            "normalizedSampledSilhouetteDifference": SILHOUETTE_AREA_TOLERANCE,
            "sampledSilhouetteHausdorff": SILHOUETTE_HAUSDORFF_TOLERANCE,
        },
    }
    if maximum_curve_error > CURVE_RECONSTRUCTION_TOLERANCE:
        raise RuntimeError("exact cubic reconstruction tolerance exceeded")
    if normalized_difference > SILHOUETTE_AREA_TOLERANCE:
        raise RuntimeError("sampled hybrid silhouette area tolerance exceeded")
    if hausdorff > SILHOUETTE_HAUSDORFF_TOLERANCE:
        raise RuntimeError("sampled hybrid silhouette boundary tolerance exceeded")
    if not complementary or before != after:
        raise RuntimeError("Phase 1 proof invariant failed")

    json_path = artifacts / "cubic-phase1-comparison.json"
    svg_path = artifacts / "cubic-phase1-comparison.svg"
    json_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_svg(svg_path, outline, current, hybrid_fragments, intersections, metrics)
    print(json.dumps(metrics, sort_keys=True))
    print(svg_path)


if __name__ == "__main__":
    main()
