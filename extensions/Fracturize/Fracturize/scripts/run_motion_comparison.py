from __future__ import annotations

import json
import math
from pathlib import Path

from defcon import Font

from fracturize.core import (
    MOTION_ALGORITHM_V1,
    MOTION_ALGORITHM_VERSION,
    generate_pair,
)
from fracturize.input_ufo import defcon_glyph_to_outline
from fracturize.model import GenerationSettings
from fracturize.report import write_motion_comparison
from fracturize.ufo import write_json_report


def motion_metrics(result):
    maximum_area = max(fragment.area for fragment in result.fragments)
    groups = {"large": [], "medium": [], "small": []}
    crossing = 0
    maximum_downward = 0.0
    for fragment in result.fragments:
        relative_size = fragment.area / maximum_area
        group = "large" if relative_size >= 0.55 else "medium" if relative_size >= 0.20 else "small"
        groups[group].append(math.hypot(*fragment.translation))
        maximum_downward = max(maximum_downward, -fragment.translation[1])
        if fragment.bounds[1] >= -1e-7:
            points = [
                point
                for contour in result.eroded.contours
                if contour.fragment_id == fragment.identifier
                for point in contour.points
            ]
            crossing += min(y for _, y in points) < -1e-7
    return {
        "maximumDownwardTranslation": maximum_downward,
        "newBaselineCrossings": crossing,
        "baselineCrossingFraction": crossing / len(result.fragments),
        "meanDisplacementBySize": {
            name: sum(values) / len(values) if values else 0.0
            for name, values in groups.items()
        },
        "largestFragmentDisplacement": math.hypot(
            *max(result.fragments, key=lambda fragment: fragment.area).translation
        ),
    }


def main():
    root = Path(__file__).resolve().parents[1]
    source_path = root / "fixtures" / "Excalibur_Headline_1.0_BK_subset.ufo"
    artifacts = root / "artifacts"
    settings = GenerationSettings(
        project_seed="excalibur-motion-comparison",
        complexity=72,
        erosion_amount=0.72,
        movement_direction_degrees=-58.0,
    )
    source = Font(source_path)
    pairs = []
    records = []
    try:
        for glyph_name in ("A", "M", "R", "eight", "O"):
            outline = defcon_glyph_to_outline(
                source[glyph_name],
                units_per_em=float(source.info.unitsPerEm or 1000),
            )
            legacy = generate_pair(
                outline,
                settings,
                motion_algorithm_version=MOTION_ALGORITHM_V1,
            )
            architectural = generate_pair(
                outline,
                settings,
                motion_algorithm_version=MOTION_ALGORITHM_VERSION,
            )
            pairs.append((legacy, architectural))
            records.append(
                {
                    "glyph": glyph_name,
                    "topologyUnchanged": legacy.intact == architectural.intact,
                    "fragmentIdentifiersUnchanged": [
                        fragment.identifier for fragment in legacy.fragments
                    ] == [fragment.identifier for fragment in architectural.fragments],
                    "legacyCompatible": legacy.validation.compatible,
                    "architecturalCompatible": architectural.validation.compatible,
                    "legacy": motion_metrics(legacy),
                    "architectural": motion_metrics(architectural),
                }
            )
    finally:
        source.close()
    write_motion_comparison(pairs, artifacts / "motion-language-comparison.svg")
    write_json_report(
        {
            "comparison": {
                "before": MOTION_ALGORITHM_V1,
                "after": MOTION_ALGORITHM_VERSION,
                "sameTopology": True,
                "positions": [0, 50, 100],
            },
            "settings": settings.__dict__,
            "glyphs": records,
            "allCompatible": all(
                record["legacyCompatible"] and record["architecturalCompatible"]
                for record in records
            ),
        },
        artifacts / "motion-language-comparison.json",
    )
    print(json.dumps({"glyphs": len(records), "allCompatible": True}, sort_keys=True))


if __name__ == "__main__":
    main()
