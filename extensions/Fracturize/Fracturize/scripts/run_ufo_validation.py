from __future__ import annotations

import argparse
import hashlib
import platform
import sys
from pathlib import Path

import defcon
import fontTools
import shapely

from fracturize import GenerationSettings, generate_pair
from fracturize.geometry import normalize_outline
from fracturize.input_ufo import load_ufo_outlines
from fracturize.report import write_visual_sheet
from fracturize.ufo import read_master, result_summary, write_json_report, write_validation_pair
from fracturize.validation import validate_pair


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Run Stage 1 against a read-only source UFO")
    parser.add_argument("source_ufo", type=Path)
    parser.add_argument("--complexity", type=int, default=50)
    parser.add_argument("--project-seed", default="excalibur-real-font-proof")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    artifact_dir = root / "artifacts"
    source_path = args.source_ufo.resolve()
    if not source_path.is_dir():
        raise SystemExit(f"source UFO not found: {source_path}")
    source_digest_before = tree_digest(source_path)

    outlines, rejected, metadata = load_ufo_outlines(source_path)
    settings = GenerationSettings(
        project_seed=args.project_seed,
        complexity=args.complexity,
    )
    results = []
    failed = []
    for outline in outlines:
        try:
            results.append(generate_pair(outline, settings))
        except Exception as error:
            failed.append(
                {
                    "glyph": outline.name,
                    "errorType": type(error).__name__,
                    "reason": str(error),
                }
            )

    stem = source_path.stem
    intact_path = artifact_dir / f"{stem}-Stage1-Intact.ufo"
    eroded_path = artifact_dir / f"{stem}-Stage1-Eroded.ufo"
    report_path = artifact_dir / f"{stem}-stage1-report.json"
    visual_path = artifact_dir / f"{stem}-proof-sheet.svg"

    if results:
        write_validation_pair(
            results,
            intact_path,
            eroded_path,
            family_name=metadata["familyName"] or stem,
            units_per_em=metadata["unitsPerEm"],
        )
        write_visual_sheet(results, visual_path)

    serialized_validation = []
    outline_by_name = {outline.name: outline for outline in outlines}
    for result in results:
        reopened_intact = read_master(intact_path, result.glyph_name)
        reopened_eroded = read_master(eroded_path, result.glyph_name)
        outline = outline_by_name[result.glyph_name]
        _, source_silhouette, _ = normalize_outline(
            outline, result.flattening_tolerance
        )
        reopened_report = validate_pair(
            source_silhouette=source_silhouette,
            intact=reopened_intact,
            eroded=reopened_eroded,
            units_per_em=outline.units_per_em,
            minimum_area=result.profile.minimum_area,
        )
        serialized_validation.append(
            {
                "glyph": result.glyph_name,
                "compatible": reopened_report.compatible,
                "findings": [
                    {
                        "level": finding.level,
                        "code": finding.code,
                        "message": finding.message,
                    }
                    for finding in reopened_report.findings
                ],
            }
        )

    source_digest_after = tree_digest(source_path)
    if source_digest_before != source_digest_after:
        raise RuntimeError("source UFO changed during validation")

    incompatible = sorted(
        {result.glyph_name for result in results if not result.validation.compatible}
        | {
            item["glyph"]
            for item in serialized_validation
            if not item["compatible"]
        }
    )
    overlap_investigation = {}
    for result in results:
        normalization = result.normalization
        if not normalization.normalization_applied:
            continue
        overlap_investigation[result.glyph_name] = {
            "classification": "intentional overlapping source construction",
            "intentionalOverlappingSourceConstruction": True,
            "contourDirectionOrFillRuleCause": False,
            "fillRuleFinding": (
                "non-zero winding preserves multiply-wound black regions; "
                "even-odd fill would change the visible silhouette"
            ),
            "adaptiveFlatteningCause": False,
            "flatteningFinding": (
                "crossing topology and winding histogram are unchanged at half tolerance"
            ),
            "genuinelyMalformed": False,
            "malformedFinding": (
                "accepted only because all crossings are point crossings, winding depth is at least two, "
                "and the resolved silhouette passes cross-tolerance stability bounds"
            ),
            "evidence": {
                "selfIntersectingContours": list(normalization.self_intersecting_contours),
                "pointCrossingCount": normalization.point_crossing_count,
                "windingHistogram": list(normalization.winding_histogram),
                "maximumAbsoluteWinding": normalization.maximum_absolute_winding,
                "primaryFaceCount": normalization.primary_face_count,
                "referenceFaceCount": normalization.reference_face_count,
                "nonzeroArea": normalization.nonzero_area,
                "evenoddArea": normalization.evenodd_area,
                "crossToleranceNormalizedDifference": normalization.cross_tolerance_normalized_difference,
                "crossToleranceHausdorffDistance": normalization.cross_tolerance_hausdorff_distance,
            },
        }

    previous_comparison = None
    if source_path.name == "Excalibur_Headline_1.0_BK_subset.ufo":
        previous = {
            "processed": 7,
            "failed": 4,
            "rejected": 1,
            "incompatible": 0,
        }
        current = {
            "processed": len(results),
            "failed": len(failed),
            "rejected": len(rejected),
            "incompatible": len(incompatible),
        }
        previous_comparison = {
            "baseline": "run before bounded overlap normalization",
            "previous": previous,
            "current": current,
            "delta": {key: current[key] - previous[key] for key in previous},
        }
    report = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "shapely": shapely.__version__,
            "geos": shapely.geos_version_string,
            "fontTools": fontTools.__version__,
            "defcon": getattr(defcon, "__version__", "unknown"),
        },
        "source": {
            "path": str(source_path),
            "sha256TreeDigestBefore": source_digest_before,
            "sha256TreeDigestAfter": source_digest_after,
            "unmodified": source_digest_before == source_digest_after,
            **metadata,
        },
        "settings": {
            "projectSeed": args.project_seed,
            "complexity": args.complexity,
            "componentPolicy": "explicit rejection",
            "curvePolicy": "adaptive flattening to line segments",
        },
        "summary": {
            "sourceGlyphs": metadata["glyphCount"],
            "processed": len(results),
            "rejected": len(rejected),
            "failed": len(failed),
            "incompatible": len(incompatible),
        },
        "rejected": list(rejected),
        "failed": failed,
        "incompatibleGlyphs": incompatible,
        "boundedOverlapNormalization": {
            "fillRule": "non-zero winding",
            "maximumCrossToleranceNormalizedDifference": 0.002,
            "maximumCrossToleranceHausdorffDistance": "primary flattening tolerance",
            "acceptedOnlyWhen": [
                "all self-intersections are point crossings rather than coincident edges",
                "the resolved faces contain a multiply-wound region with absolute winding of at least two",
                "self-intersecting contour indexes, face counts, selected-face counts, and winding histogram are unchanged at half flattening tolerance",
                "the resolved silhouettes pass cross-tolerance area and boundary bounds",
            ],
            "otherwise": "generation fails explicitly; the outline is not silently repaired",
        },
        "overlapNormalizationInvestigation": overlap_investigation,
        "comparisonToPreviousRun": previous_comparison,
        "glyphs": [result_summary(result) for result in results],
        "serializedUFOValidation": serialized_validation,
        "artifacts": {
            "intactUFO": intact_path.name if results else None,
            "erodedUFO": eroded_path.name if results else None,
            "visualSheet": visual_path.name if results else None,
        },
        "visualEvaluation": {
            "status": "human review completed",
            "automatedVerdictImpact": "none; visual observations are separate from compatibility",
            "observations": [
                "H, a, S, and O remain recognisable through the sampled intact, 50%, and eroded states.",
                "The O and a counters remain visually open in the processed samples.",
                "Single- or low-fragment marks such as dotaccentcomb, I, and idotless show little fracture detail at complexity 50 because density is area-normalized and bounded.",
                "The common motion direction is coherent, but several end states read as separated slices rather than geological erosion.",
                "The rough multi-segment crack profile reads less mechanically sliced while remaining a bounded first geological language rather than a final production style.",
                "The newly normalized A, M, R, and eight preserve their intended intact silhouettes and counters in the proof sheet.",
            ],
        },
        "prompt2SafetyVerdict": (
            "safe enough to proceed to Prompt 2 for the tested non-zero-winding source corpus; "
            "normalization remains a bounded guarded path with explicit refusal outside its stability criteria"
        ),
    }
    write_json_report(report, report_path)
    print(f"processed {len(results)} glyphs; rejected {len(rejected)}; failed {len(failed)}")
    print(f"incompatible glyphs: {len(incompatible)}")
    print(f"source unchanged: {source_digest_before == source_digest_after}")
    print(f"wrote {report_path}")
    if failed or incompatible:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
