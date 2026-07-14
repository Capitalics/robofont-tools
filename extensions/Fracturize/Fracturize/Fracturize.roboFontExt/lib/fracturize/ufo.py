from __future__ import annotations

import json
from pathlib import Path
import shutil

from defcon import Font

from .model import (
    CubicSegment,
    GenerationResult,
    LineSegment,
    MasterGlyph,
    master_contour_segments,
)

LIB_KEY = "com.fracturize.stage1.fragments"


def _draw_master(font: Font, master: MasterGlyph, *, extra_lib: dict | None = None):
    if master.name in font:
        glyph = font[master.name]
        glyph.clear()
        glyph.lib.clear()
    else:
        glyph = font.newGlyph(master.name)
    glyph.width = master.width
    glyph.unicodes = list(master.unicodes)
    point_pen = glyph.getPointPen()
    fragment_map = []
    for contour in master.contours:
        point_pen.beginPath(identifier=contour.identifier)
        for index, segment in enumerate(master_contour_segments(contour)):
            if isinstance(segment, CubicSegment):
                point_pen.addPoint(
                    segment.control1,
                    segmentType=None,
                    identifier=f"{contour.point_ids[index]}-off1",
                )
                point_pen.addPoint(
                    segment.control2,
                    segmentType=None,
                    identifier=f"{contour.point_ids[index]}-off2",
                )
                segment_type = "curve"
            else:
                segment_type = "line"
            point_pen.addPoint(
                segment.end,
                segmentType=segment_type,
                identifier=contour.point_ids[index],
            )
        point_pen.endPath()
        fragment_map.append(
            {
                "contourID": contour.identifier,
                "fragmentID": contour.fragment_id,
                "partIndex": contour.part_index,
                "isHole": contour.is_hole,
            }
        )
    glyph.lib[LIB_KEY] = fragment_map
    if extra_lib:
        glyph.lib.update(extra_lib)
    return glyph


def master_from_glyph(glyph) -> MasterGlyph:
    fragment_entries = {entry["contourID"]: entry for entry in glyph.lib[LIB_KEY]}
    contours = []
    from .model import MasterContour

    for contour in glyph:
        entry = fragment_entries[contour.identifier]
        defcon_segments = list(contour.segments)
        previous = defcon_segments[-1][-1]
        segments = []
        point_ids = []
        for defcon_segment in defcon_segments:
            oncurve = defcon_segment[-1]
            start = (float(previous.x), float(previous.y))
            end = (float(oncurve.x), float(oncurve.y))
            if oncurve.segmentType == "curve":
                control1, control2, _ = defcon_segment
                segments.append(
                    CubicSegment(
                        start,
                        (float(control1.x), float(control1.y)),
                        (float(control2.x), float(control2.y)),
                        end,
                    )
                )
            elif oncurve.segmentType == "line":
                segments.append(LineSegment(start, end))
            else:
                raise ValueError(f"unsupported generated segment type: {oncurve.segmentType!r}")
            point_ids.append(oncurve.identifier)
            previous = oncurve
        expected_prefix = f"{contour.identifier}-p0"
        start_index = next(
            (
                index
                for index, identifier in enumerate(point_ids)
                if identifier and identifier.startswith(expected_prefix)
            ),
            0,
        )
        if start_index:
            segments = segments[start_index:] + segments[:start_index]
            point_ids = point_ids[start_index:] + point_ids[:start_index]
        contours.append(
            MasterContour(
                identifier=contour.identifier,
                fragment_id=entry["fragmentID"],
                part_index=entry["partIndex"],
                is_hole=entry["isHole"],
                points=tuple(segment.end for segment in segments),
                point_ids=tuple(point_ids),
                segments=tuple(segments),
            )
        )
    return MasterGlyph(glyph.name, glyph.width, tuple(glyph.unicodes), tuple(contours))


def write_temporary_pair(result: GenerationResult, intact_path: Path, eroded_path: Path):
    for path, style_name, master in (
        (intact_path, "Fracture Intact Proof", result.intact),
        (eroded_path, "Fracture Eroded Proof", result.eroded),
    ):
        font = Font()
        font.info.familyName = "Fracturize Stage 1"
        font.info.styleName = style_name
        font.info.unitsPerEm = 1000
        _draw_master(font, master)
        font.save(path)
        font.close()


def write_validation_pair(
    results: list[GenerationResult],
    intact_path: Path,
    eroded_path: Path,
    *,
    family_name: str,
    units_per_em: float,
):
    """Write a replaceable one-shot validation pair under the artifacts folder."""

    for path, style_name, state_name in (
        (intact_path, "Stage 1 Fracture Intact", "intact"),
        (eroded_path, "Stage 1 Fracture Eroded", "eroded"),
    ):
        if path.exists():
            shutil.rmtree(path)
        font = Font()
        font.info.familyName = family_name
        font.info.styleName = style_name
        font.info.unitsPerEm = units_per_em
        for result in results:
            _draw_master(font, getattr(result, state_name))
        font.lib["com.fracturize.stage1.validationArtifact"] = True
        font.save(path)
        font.close()


def read_master(path: Path, glyph_name: str) -> MasterGlyph:
    font = Font(path)
    master = master_from_glyph(font[glyph_name])
    font.close()
    return master


def result_summary(result: GenerationResult) -> dict:
    return {
        "glyph": result.glyph_name,
        "effectiveSeed": result.effective_seed,
        "flatteningTolerance": result.flattening_tolerance,
        "complexity": result.profile.value,
        "rockEdgeDetail": result.rock_edge_detail,
        "rockEdgeRoughness": result.rock_edge_roughness,
        "normalization": {
            "fillRule": result.normalization.fill_rule,
            "applied": result.normalization.normalization_applied,
            "cause": result.normalization.cause,
            "selfIntersectingContours": list(result.normalization.self_intersecting_contours),
            "pointCrossingCount": result.normalization.point_crossing_count,
            "primaryFaceCount": result.normalization.primary_face_count,
            "referenceFaceCount": result.normalization.reference_face_count,
            "windingHistogram": list(result.normalization.winding_histogram),
            "maximumAbsoluteWinding": result.normalization.maximum_absolute_winding,
            "nonzeroArea": result.normalization.nonzero_area,
            "evenoddArea": result.normalization.evenodd_area,
            "crossToleranceSymmetricDifference": result.normalization.cross_tolerance_symmetric_difference,
            "crossToleranceNormalizedDifference": result.normalization.cross_tolerance_normalized_difference,
            "crossToleranceHausdorffDistance": result.normalization.cross_tolerance_hausdorff_distance,
        },
        "complexityProfile": {
            "targetFragments": result.profile.target_fragments,
            "actualFragments": len(result.fragments),
            "minimumArea": result.profile.minimum_area,
            "primarySplitCount": result.profile.primary_split_count,
            "secondaryProbability": result.profile.secondary_probability,
            "chipProbability": result.profile.chip_probability,
            "edgeIrregularity": result.profile.edge_irregularity,
            "detailDepth": result.profile.detail_depth,
        },
        "compatible": result.validation.compatible,
        "reconstruction": {
            "sourceArea": result.validation.reconstruction.source_area,
            "intactArea": result.validation.reconstruction.intact_area,
            "symmetricDifferenceArea": result.validation.reconstruction.symmetric_difference_area,
            "normalizedSymmetricDifference": result.validation.reconstruction.normalized_symmetric_difference,
            "hausdorffDistance": result.validation.reconstruction.hausdorff_distance,
        },
        "findings": [
            {"level": finding.level, "code": finding.code, "message": finding.message}
            for finding in result.validation.findings
        ],
        "notes": list(result.notes),
    }


def write_json_report(data, path: Path):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
