from __future__ import annotations

"""Generate the standalone Phase 2 hybrid-fragment comparison for `O`."""

import hashlib
import json
from pathlib import Path

from defcon import Font
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


SETTINGS = GenerationSettings(
    project_seed="cubic-phase2",
    complexity=30,
    rock_edge_detail=0,
)
SAMPLES_PER_CUBIC = 1024


def tree_digest(path):
    digest = hashlib.sha256()
    for item in sorted(file for file in path.rglob("*") if file.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def source_contour_points(contour, samples=SAMPLES_PER_CUBIC):
    points = []
    for segment in contour.segments:
        if isinstance(segment, CubicSegment):
            points.extend(cubic_point(segment, index / samples) for index in range(samples))
        else:
            points.append(segment.start)
    return points


def source_path(outline):
    paths = []
    for contour in outline.contours:
        segments = contour.segments
        commands = [f"M {segments[0].start[0]:.8f} {-segments[0].start[1]:.8f}"]
        for segment in segments:
            if isinstance(segment, CubicSegment):
                commands.append(
                    "C "
                    f"{segment.control1[0]:.8f} {-segment.control1[1]:.8f} "
                    f"{segment.control2[0]:.8f} {-segment.control2[1]:.8f} "
                    f"{segment.end[0]:.8f} {-segment.end[1]:.8f}"
                )
            else:
                commands.append(f"L {segment.end[0]:.8f} {-segment.end[1]:.8f}")
        commands.append("Z")
        paths.append(" ".join(commands))
    return " ".join(paths)


def polygonal_paths(master):
    paths = []
    for contour in master.contours:
        commands = [f"M {contour.points[0][0]:.8f} {-contour.points[0][1]:.8f}"]
        commands.extend(f"L {x:.8f} {-y:.8f}" for x, y in contour.points[1:])
        commands.append("Z")
        paths.append(" ".join(commands))
    return paths


def hybrid_paths(glyph):
    paths = []
    fracture_lines = []
    nodes = []
    for fragment in glyph.fragments:
        for contour in fragment.contours:
            first = contour.segments[0].geometry.start
            commands = [f"M {first[0]:.8f} {-first[1]:.8f}"]
            for segment in contour.segments:
                geometry = segment.geometry
                if isinstance(geometry, CubicSegment):
                    commands.append(
                        "C "
                        f"{geometry.control1[0]:.8f} {-geometry.control1[1]:.8f} "
                        f"{geometry.control2[0]:.8f} {-geometry.control2[1]:.8f} "
                        f"{geometry.end[0]:.8f} {-geometry.end[1]:.8f}"
                    )
                else:
                    commands.append(f"L {geometry.end[0]:.8f} {-geometry.end[1]:.8f}")
                    fracture_lines.append(geometry)
                if segment.kind == "exterior" and segment.source_t_range[0] > 0:
                    nodes.append(geometry.start)
            commands.append("Z")
            paths.append(" ".join(commands))
    return paths, fracture_lines, nodes


def write_svg(path, outline, guide, proof, metrics):
    middle = interpolate_hybrid_glyph(proof.intact, proof.eroded, 0.5)
    columns = (
        (25, "Original cubic source", "source"),
        (725, "Current polygonal macro result", guide.intact),
        (1425, "Hybrid intact", proof.intact),
        (2125, "Hybrid interpolation 50%", middle),
        (2825, "Hybrid eroded", proof.eroded),
    )
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="3500" height="920" viewBox="0 0 3500 920">',
        '<rect width="100%" height="100%" fill="#f4f0e7"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#292622}.title{font-size:24px}.meta{font-size:15px;fill:#665f55}.source{fill:#292622;fill-rule:nonzero}.fragment{fill:#292622;stroke:#d56b4e;stroke-width:1.2;fill-rule:nonzero}.fracture{fill:none;stroke:#ee563b;stroke-width:2.5}.node{fill:#2484a8;stroke:white;stroke-width:1.5}</style>',
    ]
    for x, title, content in columns:
        rows.append(f'<text class="title" x="{x}" y="38">{title}</text>')
        rows.append(f'<g transform="translate({x},790)">')
        if content == "source":
            rows.append(f'<path class="source" d="{source_path(outline)}"/>')
        elif content is guide.intact:
            for polygon_path in polygonal_paths(content):
                rows.append(f'<path class="fragment" d="{polygon_path}"/>')
        else:
            paths, fracture_lines, nodes = hybrid_paths(content)
            for hybrid_path in paths:
                rows.append(f'<path class="fragment" d="{hybrid_path}"/>')
            # Duplicate shared lines are intentionally collapsed visually; the
            # JSON records both complementary uses.
            unique_lines = {
                tuple(sorted((line.start, line.end))): line for line in fracture_lines
            }
            for line in unique_lines.values():
                rows.append(
                    f'<path class="fracture" d="M {line.start[0]:.8f} {-line.start[1]:.8f} '
                    f'L {line.end[0]:.8f} {-line.end[1]:.8f}"/>'
                )
            if content is proof.intact:
                for node in sorted(set(nodes)):
                    rows.append(
                        f'<circle class="node" cx="{node[0]:.8f}" '
                        f'cy="{-node[1]:.8f}" r="4.5"/>'
                    )
        rows.append("</g>")
    rows.extend(
        [
            f'<text class="meta" x="25" y="850">{metrics["fragmentCount"]} fragments; {metrics["preservedCubicSegments"]} exact exterior cubic intervals; {metrics["newExteriorIntersectionNodes"]} new nodes</text>',
            f'<text class="meta" x="25" y="876">{metrics["uniqueInternalLineSegments"]} unique internal line segments; compatible: {str(metrics["compatible"]).lower()}</text>',
            f'<text class="meta" x="25" y="902">normalized reconstruction error {metrics["normalizedSilhouetteDifference"]:.3e}; Hausdorff {metrics["silhouetteHausdorffDistance"]:.3e}</text>',
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

    source = Polygon(
        source_contour_points(outline.contours[0]),
        [source_contour_points(outline.contours[1])],
    )
    intact = hybrid_glyph_geometry(proof.intact, SAMPLES_PER_CUBIC)
    normalized_difference = source.symmetric_difference(intact).area / source.area
    hausdorff = source.boundary.hausdorff_distance(intact.boundary)
    uses = shared_internal_edge_uses(proof.intact)
    complementary = all(
        len(records) == 2
        and records[0][1].start == records[1][1].end
        and records[0][1].end == records[1][1].start
        for records in uses.values()
    )
    interpolation_valid = True
    for factor in (0.0, 0.25, 0.5, 0.75, 1.0):
        interpolated = interpolate_hybrid_glyph(proof.intact, proof.eroded, factor)
        geometry = hybrid_glyph_geometry(interpolated, 128)
        interpolation_valid &= geometry.is_valid and geometry.area > 0
    compatible = (
        structural_signature(proof.intact) == structural_signature(proof.eroded)
        and complementary
        and interpolation_valid
    )
    metrics = {
        "glyph": "O",
        "macroCrackPolylines": len(crack_lines),
        "fragmentCount": len(proof.intact.fragments),
        "preservedCubicSegments": sum(
            segment.kind == "exterior"
            for fragment in proof.intact.fragments
            for contour in fragment.contours
            for segment in contour.segments
        ),
        "newExteriorIntersectionNodes": len(proof.new_exterior_nodes),
        "additionalExteriorApproximationNodes": 0,
        "logicalSharedInternalEdges": len(proof.shared_edge_ids),
        "uniqueInternalLineSegments": len(uses),
        "internalLineSegmentInstances": sum(len(records) for records in uses.values()),
        "sharedInternalEdgesComplementary": complementary,
        "counterCount": len(intact.interiors),
        "normalizedSilhouetteDifference": normalized_difference,
        "silhouetteHausdorffDistance": hausdorff,
        "structurallyCompatible": (
            structural_signature(proof.intact) == structural_signature(proof.eroded)
        ),
        "sampledInterpolationValid": interpolation_valid,
        "compatible": compatible,
        "sourceUnmodified": tree_digest(fixture) == before,
        "settings": {
            "projectSeed": SETTINGS.project_seed,
            "complexity": SETTINGS.complexity,
            "rockEdgeDetail": SETTINGS.rock_edge_detail,
        },
        "unsupported": [
            "components",
            "overlapping or self-intersecting source contours",
            "tangent or collinear crack/source intersections",
            "source line segments requiring a new split",
            "ambiguous face graphs or unsupported nested contour arrangements",
        ],
    }
    if not compatible or len(intact.interiors) != 1:
        raise RuntimeError("Phase 2 compatibility or counter invariant failed")
    if normalized_difference > 1e-6 or hausdorff > 1e-3:
        raise RuntimeError("Phase 2 reconstruction tolerance exceeded")
    if not metrics["sourceUnmodified"]:
        raise RuntimeError("source fixture changed")

    json_path = artifacts / "cubic-phase2-comparison.json"
    svg_path = artifacts / "cubic-phase2-comparison.svg"
    json_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_svg(svg_path, outline, guide, proof, metrics)
    print(json.dumps(metrics, sort_keys=True))
    print(svg_path)


if __name__ == "__main__":
    main()
