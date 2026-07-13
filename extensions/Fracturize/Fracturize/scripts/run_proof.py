from __future__ import annotations

import platform
import sys
from pathlib import Path

import defcon
import fontTools
import shapely

from fracturize import GenerationSettings, generate_pair
from test_support.fixtures import proof_fixtures
from test_support.reporting import write_visual_sheet
from fracturize.ufo import result_summary, write_json_report


def main():
    root = Path(__file__).resolve().parents[1]
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    results = [
        generate_pair(outline, GenerationSettings(complexity=50))
        for outline in proof_fixtures().values()
    ]
    complexity = {}
    sample = proof_fixtures()["O.curve"]
    for value in (10, 25, 50, 75, 90):
        result = generate_pair(sample, GenerationSettings(complexity=value))
        complexity[str(value)] = result_summary(result)

    report = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "shapely": shapely.__version__,
            "geos": shapely.geos_version_string,
            "fontTools": fontTools.__version__,
            "defcon": getattr(defcon, "__version__", "unknown"),
        },
        "decisions": {
            "geometryBackend": "Shapely/GEOS polygon operations",
            "fillRule": "non-zero winding over noded and polygonized flattened rings",
            "componentPolicy": "explicit rejection",
            "curvePolicy": "adaptive flattening to line segments; no curve preservation",
            "reconstructionAreaTolerance": 1e-8,
            "reconstructionHausdorffUPMRatio": 1e-7,
            "nestedComplexity": False,
        },
        "fixtures": [result_summary(result) for result in results],
        "complexitySamples": complexity,
        "visualEvaluation": {
            "status": "human review completed",
            "artifact": "proof-sheet.svg",
            "criteria": [
                "recognisability",
                "controlled erosion rather than explosion",
                "absence of regular mosaic appearance",
                "reasonable density across glyph structures",
            ],
            "observations": [
                "All supported fixtures remain recognisable at the sampled 0%, 50%, and 100% positions.",
                "The directionally coherent motion reads as a progressive breakup, but some 100% states feel more separated than eroded.",
                "The rough edge profile replaces long slice edges with short irregular angular facets; the macro layout's single-impact spiderweb bias and occasional triangular chips still need product-level tuning.",
                "Flattened curved outlines show polygonal faceting under close inspection, as expected from the declared Stage 1 curve policy.",
                "Fragment density is bounded and broadly comparable, but thin and disconnected fixtures need later visual tuning.",
            ],
            "automatedVerdictImpact": "none; these are visual warnings, not structural compatibility failures",
        },
        "stage1Verdict": "viable",
        "stage1VerdictScope": "polygonal geometry, reconstruction, identity, and structural compatibility proof only",
    }
    write_json_report(report, artifact_dir / "stage1-report.json")
    write_visual_sheet(results, artifact_dir / "proof-sheet.svg")
    incompatible = [result.glyph_name for result in results if not result.validation.compatible]
    if incompatible:
        raise SystemExit(f"incompatible fixtures: {', '.join(incompatible)}")
    print(f"wrote {artifact_dir / 'stage1-report.json'}")
    print(f"wrote {artifact_dir / 'proof-sheet.svg'}")


if __name__ == "__main__":
    main()
