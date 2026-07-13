from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from fracturize import GenerationSettings, generate_pair
from fracturize.core import (
    CLEAN_MACRO_COMPARISON_VERSION,
    TOPOLOGY_VERSION,
    boundary_point_provenance,
    complexity_profile,
    derive_effective_seed,
    edge_profile_parameters,
    generate_clean_macro_topology,
    generate_crack_mesh,
    generate_macro_crack_mesh,
    generate_topology,
)
from fracturize.geometry import adaptive_flattening_tolerance, normalize_outline
from fracturize.input_ufo import load_ufo_outlines
from fracturize.report import write_edge_profile_comparison
from fracturize.ufo import result_summary, write_json_report


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def mesh_digest(lines) -> str:
    digest = hashlib.sha256()
    for line in lines:
        digest.update(line.wkb)
    return digest.hexdigest()


def segment_statistics(lines) -> dict:
    lengths = []
    directions = []
    for line in lines:
        coordinates = list(line.coords)
        for first, second in zip(coordinates, coordinates[1:]):
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            lengths.append(math.hypot(dx, dy))
            directions.append(round(math.degrees(math.atan2(dy, dx)) % 180, 1))
    ordered = sorted(lengths)
    return {
        "crackLines": len(lines),
        "segments": len(lengths),
        "minimumSegmentLength": min(lengths) if lengths else 0,
        "medianSegmentLength": ordered[len(ordered) // 2] if ordered else 0,
        "maximumSegmentLength": max(lengths) if lengths else 0,
        "distinctSegmentDirectionsAtTenthDegree": len(set(directions)),
        "simpleLines": sum(line.is_simple for line in lines),
    }


def intersection_graph(lines) -> tuple[tuple[int, int], ...]:
    return tuple(
        (first, second)
        for first in range(len(lines))
        for second in range(first)
        if lines[first].distance(lines[second]) <= 1e-6
    )


def serialized_provenance(provenance) -> dict:
    return {
        key: {"count": len(points), "points": [list(point) for point in points]}
        for key, points in provenance.items()
    }


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "fixtures" / "Excalibur_Headline_1.0_BK_subset.ufo"
    artifact_dir = root / "artifacts"
    before = tree_digest(source)
    outlines, rejected, _ = load_ufo_outlines(source)
    selected = {"A", "M", "R", "eight", "O", "S"}
    settings = GenerationSettings(project_seed="edge-profile-comparison", complexity=72)
    pairs = []
    glyph_records = []
    for outline in outlines:
        if outline.name not in selected:
            continue
        clean = generate_pair(
            outline,
            settings,
            topology_generator=generate_clean_macro_topology,
            topology_version=CLEAN_MACRO_COMPARISON_VERSION,
        )
        rough = generate_pair(
            outline,
            settings,
            topology_generator=generate_topology,
            topology_version=TOPOLOGY_VERSION,
        )
        tolerance = adaptive_flattening_tolerance(outline.units_per_em)
        _, silhouette, _ = normalize_outline(outline, tolerance)
        profile = complexity_profile(
            settings.complexity,
            area=silhouette.area,
            units_per_em=outline.units_per_em,
        )
        seed = derive_effective_seed(settings, outline.name)
        macro_mesh = generate_macro_crack_mesh(silhouette, profile, seed, outline.units_per_em)
        rough_mesh = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
        clean_pieces = generate_clean_macro_topology(
            silhouette, profile, seed, outline.units_per_em
        )
        rough_pieces = generate_topology(silhouette, profile, seed, outline.units_per_em)
        provenance_tolerance = max(tolerance * 0.01, 1e-6)
        clean_provenance = boundary_point_provenance(
            silhouette,
            clean_pieces,
            macro_mesh,
            distance_tolerance=provenance_tolerance,
        )
        rough_provenance = boundary_point_provenance(
            silhouette,
            rough_pieces,
            rough_mesh,
            distance_tolerance=provenance_tolerance,
        )
        junctions_preserved = all(
            tuple(macro.coords[0]) == tuple(rough_line.coords[0])
            and tuple(macro.coords[-1]) == tuple(rough_line.coords[-1])
            for macro, rough_line in zip(macro_mesh, rough_mesh, strict=True)
        )
        pairs.append((clean, rough))
        glyph_records.append(
            {
                "glyph": outline.name,
                "macroLayoutDigest": mesh_digest(macro_mesh),
                "roughProfileDigest": mesh_digest(rough_mesh),
                "sameLineCount": len(macro_mesh) == len(rough_mesh),
                "allMacroEndpointsPreserved": junctions_preserved,
                "intersectionGraphPreserved": (
                    intersection_graph(macro_mesh) == intersection_graph(rough_mesh)
                ),
                "clean": result_summary(clean),
                "rough": result_summary(rough),
                "cleanMesh": segment_statistics(macro_mesh),
                "roughMesh": segment_statistics(rough_mesh),
                "cleanBoundaryPoints": serialized_provenance(clean_provenance),
                "roughBoundaryPoints": serialized_provenance(rough_provenance),
            }
        )

    visual_path = artifact_dir / "edge-profile-comparison.svg"
    report_path = artifact_dir / "edge-profile-comparison.json"
    write_edge_profile_comparison(pairs, visual_path)
    after = tree_digest(source)
    parameters = edge_profile_parameters(settings.complexity, 1000)
    report = {
        "purpose": "pre-audit clean-macro versus rough-edge comparison using identical fracture layouts",
        "auditStarted": False,
        "source": {
            "path": str(source.relative_to(root)),
            "digestBefore": before,
            "digestAfter": after,
            "unmodified": before == after,
        },
        "settings": {
            "projectSeed": settings.project_seed,
            "complexity": settings.complexity,
            "cleanTopologyVersion": CLEAN_MACRO_COMPARISON_VERSION,
            "roughTopologyVersion": TOPOLOGY_VERSION,
            "edgeProfileAt1000UPM": asdict(parameters),
        },
        "rejectedSourceGlyphs": list(rejected),
        "glyphs": glyph_records,
        "boundaryInterpretation": {
            "requiredCrackBoundaryPoints": "actual rough crack intersections with exterior or counter boundaries; these shared nodes are necessary for closed complementary fragments",
            "baselineFlatteningBoundaryPoints": "vertices already present in the normalized adaptively flattened boundary",
            "clippingArtifactBoundaryPoints": "residual exterior nodes matching neither a crack intersection nor a baseline vertex; these are not semantically required crack points",
        },
        "visualArtifact": visual_path.name,
    }
    write_json_report(report, report_path)
    if before != after:
        raise RuntimeError("source UFO changed during edge-profile comparison")
    if not all(clean.validation.compatible and rough.validation.compatible for clean, rough in pairs):
        raise RuntimeError("edge-profile comparison produced an incompatible master pair")
    if not all(record["allMacroEndpointsPreserved"] for record in glyph_records):
        raise RuntimeError("rough edge profile moved a macro crack endpoint")
    if not all(record["intersectionGraphPreserved"] for record in glyph_records):
        raise RuntimeError("rough edge profile changed the macro intersection graph")
    print(json.dumps({"glyphs": len(glyph_records), "sourceUnmodified": True}, sort_keys=True))
    print(f"visual: {visual_path}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
