from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from .geometry import master_contours_to_union
from .model import (
    CubicSegment,
    ComplexityProfile,
    Fragment,
    GenerationResult,
    MasterContour,
    MasterGlyph,
    LineSegment,
    NormalizationDiagnostics,
    master_contour_segments,
)
from .validation import validate_pair

TOPOLOGY_FORMAT = "com.fracturize.topology"
TOPOLOGY_FORMAT_VERSION = 3


def _segment_to_dict(segment):
    if isinstance(segment, CubicSegment):
        return {
            "type": "curve",
            "start": list(segment.start),
            "control1": list(segment.control1),
            "control2": list(segment.control2),
            "end": list(segment.end),
        }
    return {"type": "line", "start": list(segment.start), "end": list(segment.end)}


def _segment_from_dict(data):
    start = tuple(map(float, data["start"]))
    end = tuple(map(float, data["end"]))
    if data["type"] == "curve":
        return CubicSegment(
            start,
            tuple(map(float, data["control1"])),
            tuple(map(float, data["control2"])),
            end,
        )
    if data["type"] == "line":
        return LineSegment(start, end)
    raise ValueError(f"unsupported stored segment type: {data['type']!r}")


def _contour_to_dict(contour: MasterContour) -> dict:
    return {
        "identifier": contour.identifier,
        "fragmentID": contour.fragment_id,
        "partIndex": contour.part_index,
        "isHole": contour.is_hole,
        "points": [list(point) for point in contour.points],
        "pointIDs": list(contour.point_ids),
        "segments": [
            _segment_to_dict(segment) for segment in master_contour_segments(contour)
        ],
    }


def _contour_from_dict(data: dict) -> MasterContour:
    segments = tuple(_segment_from_dict(item) for item in data.get("segments", ()))
    return MasterContour(
        identifier=data["identifier"],
        fragment_id=data["fragmentID"],
        part_index=int(data["partIndex"]),
        is_hole=bool(data["isHole"]),
        points=tuple((float(x), float(y)) for x, y in data["points"]),
        point_ids=tuple(data["pointIDs"]),
        segments=segments,
    )


def topology_to_dict(result: GenerationResult, *, units_per_em: float) -> dict:
    return {
        "format": TOPOLOGY_FORMAT,
        "formatVersion": TOPOLOGY_FORMAT_VERSION,
        "glyphName": result.glyph_name,
        "unitsPerEm": units_per_em,
        "width": result.intact.width,
        "unicodes": list(result.intact.unicodes),
        "effectiveSeed": result.effective_seed,
        "flatteningTolerance": result.flattening_tolerance,
        "rockEdgeDetail": result.rock_edge_detail,
        "outlineReconstructionVersion": result.outline_reconstruction_version,
        "profile": asdict(result.profile),
        "normalization": asdict(result.normalization),
        "fragments": [
            {
                "identifier": fragment.identifier,
                "area": fragment.area,
                "centroid": list(fragment.centroid),
                "bounds": list(fragment.bounds),
                "transformOrigin": list(fragment.transform_origin),
                "intactContours": [
                    _contour_to_dict(contour) for contour in fragment.intact_contours
                ],
            }
            for fragment in result.fragments
        ],
        "notes": list(result.notes),
    }


def topology_from_dict(data: dict) -> tuple[GenerationResult, float]:
    format_version = data.get("formatVersion")
    if data.get("format") != TOPOLOGY_FORMAT or format_version not in {1, 2, 3}:
        raise ValueError("unsupported topology format")
    profile_data = data["profile"]
    profile = ComplexityProfile(**profile_data)
    normalization_data = dict(data["normalization"])
    normalization_data["self_intersecting_contours"] = tuple(
        normalization_data["self_intersecting_contours"]
    )
    normalization_data["winding_histogram"] = tuple(normalization_data["winding_histogram"])
    normalization = NormalizationDiagnostics(**normalization_data)
    fragments = []
    intact_contours = []
    for item in data["fragments"]:
        contours = tuple(_contour_from_dict(contour) for contour in item["intactContours"])
        intact_contours.extend(contours)
        fragments.append(
            Fragment(
                identifier=item["identifier"],
                area=float(item["area"]),
                centroid=tuple(item["centroid"]),
                bounds=tuple(item["bounds"]),
                transform_origin=tuple(item["transformOrigin"]),
                intact_contours=contours,
                translation=(0.0, 0.0),
                rotation_degrees=0.0,
                scale=1.0,
            )
        )
    intact = MasterGlyph(
        data["glyphName"],
        float(data["width"]),
        tuple(data["unicodes"]),
        tuple(intact_contours),
    )
    silhouette = master_contours_to_union(intact.contours)
    units_per_em = float(data["unitsPerEm"])
    validation = validate_pair(
        source_silhouette=silhouette,
        intact=intact,
        eroded=intact,
        units_per_em=units_per_em,
        minimum_area=profile.minimum_area,
    )
    result = GenerationResult(
        glyph_name=data["glyphName"],
        effective_seed=int(data["effectiveSeed"]),
        flattening_tolerance=float(data["flatteningTolerance"]),
        # Version 1 coupled micro detail to complexity. Reading that value back
        # preserves motion-only regeneration for projects made before the
        # independent control existed.
        rock_edge_detail=int(data.get("rockEdgeDetail", profile.value)),
        profile=profile,
        normalization=normalization,
        fragments=tuple(fragments),
        intact=intact,
        eroded=intact,
        validation=validation,
        notes=tuple(data.get("notes", ())),
        outline_reconstruction_version=data.get(
            "outlineReconstructionVersion", "polygonal-v1"
        ),
    )
    return result, units_per_em


def write_topology(result: GenerationResult, path: Path, *, units_per_em: float) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        topology_to_dict(result, units_per_em=units_per_em),
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_topology(path: Path) -> tuple[GenerationResult, float]:
    return topology_from_dict(json.loads(path.read_text(encoding="utf-8")))


def topology_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
