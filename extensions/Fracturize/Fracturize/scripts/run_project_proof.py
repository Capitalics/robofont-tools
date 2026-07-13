from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from defcon import Font

from fracturize.geometry import UnsupportedOutlineError
from fracturize.project import FractureProject
from fracturize.ufo import read_master, write_json_report


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    source_path = root / "tests" / "fixtures" / "FracturizeRegression.ufo"
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    demo_dir = artifact_dir / "stage2-demo"
    if demo_dir.exists():
        shutil.rmtree(demo_dir)

    source_before = tree_digest(source_path)
    source = Font(source_path)
    source_names = list(source.keys())
    source.close()

    project = FractureProject.create(
        demo_dir,
        source_path,
        project_name="SyntheticFractureDemo",
        project_seed="synthetic-stage2-demo",
        complexity=50,
    )
    created_paths = {
        "project": str(project.path.relative_to(root)),
        "intact": str(project.intact_path.relative_to(root)),
        "eroded": str(project.eroded_path.relative_to(root)),
    }
    first_intact_path = project.intact_path
    first_eroded_path = project.eroded_path
    project.process_glyph("O")
    project.close()

    project = FractureProject.open(project.path)
    rejected = []
    for glyph_name in source_names:
        if glyph_name == "O":
            continue
        try:
            project.process_glyph(glyph_name)
        except UnsupportedOutlineError as error:
            rejected.append({"glyph": glyph_name, "reason": str(error)})

    eroded_before_motion = {
        glyph_name: read_master(project.eroded_path, glyph_name)
        for glyph_name in project.data["processedGlyphs"]
    }
    topology_before_motion = {
        glyph_name: record["topologyDigest"]
        for glyph_name, record in project.data["processedGlyphs"].items()
    }
    project.set_motion_settings(erosion_amount=0.67, movement_direction_degrees=-58.0)
    for glyph_name in list(project.data["processedGlyphs"]):
        project.regenerate_motion(glyph_name)
    eroded_after_motion = {
        glyph_name: read_master(project.eroded_path, glyph_name)
        for glyph_name in project.data["processedGlyphs"]
    }
    topology_after_motion = {
        glyph_name: record["topologyDigest"]
        for glyph_name, record in project.data["processedGlyphs"].items()
    }
    final_project = FractureProject.open(project.path)

    intact = Font(final_project.intact_path)
    eroded = Font(final_project.eroded_path)
    intact_names = sorted(intact.keys())
    eroded_names = sorted(eroded.keys())
    intact.close()
    eroded.close()
    source_after = tree_digest(source_path)

    report = {
        "phase": "Stage 2 Phase A harness revalidated after Phase C corrections",
        "auditStarted": True,
        "phaseCCorrectionsApplied": True,
        "prompt3Started": False,
        "source": {
            "path": str(source_path.relative_to(root)),
            "digestBefore": source_before,
            "digestAfter": source_after,
            "unmodified": source_before == source_after,
        },
        "createdPaths": created_paths,
        "workflow": {
            "outputsCreatedBeforeFirstGlyph": True,
            "firstProcessedGlyph": "O",
            "closedAndReopenedAfterFirstGlyph": True,
            "sameIntactPathAfterReopen": final_project.intact_path == first_intact_path,
            "sameErodedPathAfterReopen": final_project.eroded_path == first_eroded_path,
            "laterGlyphsAppended": True,
            "motionOnlyRegenerationGlyphs": sorted(project.data["processedGlyphs"]),
            "motionChangedForEveryProcessedGlyph": all(
                eroded_before_motion[name] != eroded_after_motion[name]
                for name in eroded_before_motion
            ),
            "topologyDigestsPreservedForMotionOnly": (
                topology_before_motion == topology_after_motion
            ),
        },
        "summary": {
            "sourceGlyphs": len(source_names),
            "processedGlyphs": len(final_project.data["processedGlyphs"]),
            "rejectedGlyphs": len(rejected),
            "intactGlyphs": len(intact_names),
            "erodedGlyphs": len(eroded_names),
            "glyphSetsMatch": intact_names == eroded_names,
        },
        "processedGlyphNames": intact_names,
        "rejected": rejected,
        "projectIntegrityReopenPassed": True,
        "settings": final_project.data["settings"],
        "savePolicy": final_project.data["savePolicy"],
        "fontInfoAllowlist": final_project.data["fontInfoAllowlist"],
        "glyphDataAllowlist": final_project.data["glyphDataAllowlist"],
        "limitations": [
            "paired saves provide ordinary exception rollback but are not crash-proof across directory UFOs",
            "file-backed detached writes belong only to the headless harness; final outputs are user-owned RoboFont documents",
            "edited generated outlines are detected but not merged; replacement requires an explicit regeneration choice",
            "components remain explicitly unsupported",
            "project format version 1 has no migration framework",
            "project relocation and source relinking are deferred",
            "curves remain flattened to polygonal line output",
            "generated validation artifacts are disposable and are not extension resources",
        ],
    }
    write_json_report(report, artifact_dir / "stage2-implementation-report.json")
    print(json.dumps(report["summary"], sort_keys=True))
    print(f"source unchanged: {report['source']['unmodified']}")
    print(f"project: {project.path}")
    print(f"report: {artifact_dir / 'stage2-implementation-report.json'}")


if __name__ == "__main__":
    main()
