from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from fracturize import GenerationSettings, generate_pair
from fracturize.core import (
    RECURSIVE_TOPOLOGY_VERSION,
    TOPOLOGY_VERSION,
    boundary_point_provenance,
    complexity_profile,
    derive_effective_seed,
    generate_crack_mesh,
    generate_recursive_topology,
    generate_topology,
)
from fracturize.geometry import adaptive_flattening_tolerance, normalize_outline
from fracturize.input_ufo import load_ufo_outlines
from test_support.reporting import write_topology_comparison
from fracturize.ufo import result_summary, write_json_report


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
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
    return {
        "crackLines": len(lines),
        "segments": len(lengths),
        "minimumSegmentLength": min(lengths) if lengths else 0,
        "maximumSegmentLength": max(lengths) if lengths else 0,
        "distinctSegmentDirectionsAtTenthDegree": len(set(directions)),
    }


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "tests" / "fixtures" / "FracturizeRegression.ufo"
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    digest_before = tree_digest(source)
    outlines, rejected, _ = load_ufo_outlines(source)
    selected = {"A", "M", "R", "eight", "O", "S"}
    settings = GenerationSettings(project_seed="topology-language-comparison", complexity=72)
    pairs = []
    records = []
    for outline in outlines:
        if outline.name not in selected:
            continue
        old = generate_pair(
            outline,
            settings,
            topology_generator=generate_recursive_topology,
            topology_version=RECURSIVE_TOPOLOGY_VERSION,
        )
        new = generate_pair(
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
        mesh = generate_crack_mesh(silhouette, profile, seed, outline.units_per_em)
        pieces = generate_topology(silhouette, profile, seed, outline.units_per_em)
        provenance = boundary_point_provenance(
            silhouette,
            pieces,
            mesh,
            distance_tolerance=max(tolerance * 0.01, 1e-6),
        )
        pairs.append((old, new))
        records.append(
            {
                "glyph": outline.name,
                "old": result_summary(old),
                "new": result_summary(new),
                "mesh": segment_statistics(mesh),
                "outerBoundaryPointInsertion": {
                    key: {"count": len(points), "points": [list(point) for point in points]}
                    for key, points in provenance.items()
                },
            }
        )

    visual_path = artifact_dir / "topology-language-comparison.svg"
    report_path = artifact_dir / "topology-language-comparison.json"
    write_topology_comparison(pairs, visual_path)
    digest_after = tree_digest(source)
    report = {
        "purpose": "pre-audit comparison of recursive slicing and branching crack mesh",
        "auditStarted": False,
        "source": {
            "path": str(source.relative_to(root)),
            "digestBefore": digest_before,
            "digestAfter": digest_after,
            "unmodified": digest_before == digest_after,
        },
        "settings": {
            "complexity": settings.complexity,
            "projectSeed": settings.project_seed,
            "oldTopologyVersion": RECURSIVE_TOPOLOGY_VERSION,
            "newTopologyVersion": TOPOLOGY_VERSION,
        },
        "rejectedSourceGlyphs": list(rejected),
        "glyphs": records,
        "boundaryInterpretation": {
            "requiredCrackBoundaryPoints": "nodes where crack linework actually meets any normalized filled-silhouette boundary, including counter boundaries",
            "baselineFlatteningBoundaryPoints": "pre-existing vertices of the adaptively flattened normalized silhouette; not introduced by fracture clipping",
            "clippingArtifactBoundaryPoints": "new exterior vertices which match neither a crack-boundary intersection nor a baseline flattened vertex",
            "futureCurvePreservation": "untouched exterior intervals can theoretically retain source cubics, but only after adding source-curve parameter provenance and splitting those curves at true crack intersections; the current polygonal pipeline intentionally lacks that provenance",
        },
        "visualArtifact": visual_path.name,
    }
    write_json_report(report, report_path)
    if digest_before != digest_after:
        raise RuntimeError("source UFO changed during topology comparison")
    if not all(old.validation.compatible and new.validation.compatible for old, new in pairs):
        raise RuntimeError("comparison produced an incompatible master pair")
    print(json.dumps({"glyphs": len(records), "sourceUnmodified": True}, sort_keys=True))
    print(f"visual: {visual_path}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
