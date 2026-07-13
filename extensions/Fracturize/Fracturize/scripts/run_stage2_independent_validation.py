from __future__ import annotations

import json
import shutil
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTFont
from fontTools.ufoLib import UFOReader
from fontmake.font_project import FontProject
from shapely.geometry import LinearRing

from fracturize.project import FractureProject
from fracturize.ufo import write_json_report


POSITIONS = (0, 10, 25, 50, 75, 90, 100)


class GlyphInfo:
    pass


def read_glyph(glyph_set, name):
    info = GlyphInfo()
    pen = RecordingPointPen()
    glyph_set.readGlyph(name, info, pen)
    contours = []
    current = None
    for operation, args, kwargs in pen.value:
        if operation == "beginPath":
            current = {"identifier": kwargs.get("identifier"), "points": []}
        elif operation == "addPoint":
            point, segment_type, smooth, point_name = args
            current["points"].append(
                {
                    "position": tuple(point),
                    "segmentType": segment_type,
                    "smooth": smooth,
                    "name": point_name,
                    "identifier": kwargs.get("identifier"),
                }
            )
        elif operation == "endPath":
            contours.append(current)
            current = None
        elif operation == "addComponent":
            raise AssertionError(f"generated glyph {name} unexpectedly contains a component")
    return {
        "width": info.width,
        "unicodes": tuple(getattr(info, "unicodes", ())),
        "lib": info.lib,
        "contours": contours,
    }


def signed_area(points):
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:] + points[:1])
    )


def main():
    root = Path(__file__).resolve().parents[1]
    project_path = root / "artifacts" / "stage2-demo" / "ExcaliburFractureDemo.fracturize.json"
    project = FractureProject.open(project_path)
    if project.edited_outputs:
        raise AssertionError(f"unexpected edited outputs: {project.edited_outputs}")

    readers = {
        "intact": UFOReader(project.intact_path),
        "eroded": UFOReader(project.eroded_path),
    }
    glyph_sets = {role: reader.getGlyphSet() for role, reader in readers.items()}
    names = sorted(glyph_sets["intact"].keys())
    metadata_mismatches = []
    structure_mismatches = []
    identity_mismatches = []
    winding_mismatches = []
    self_intersections = 0
    zero_areas = 0
    total_contours = 0
    total_points = 0
    line_points = 0
    off_curve_points = 0
    if names != sorted(glyph_sets["eroded"].keys()):
        structure_mismatches.append("glyph sets differ")
    for name in names:
        sides = {role: read_glyph(glyph_set, name) for role, glyph_set in glyph_sets.items()}
        if (sides["intact"]["width"], sides["intact"]["unicodes"]) != (
            sides["eroded"]["width"],
            sides["eroded"]["unicodes"],
        ):
            metadata_mismatches.append(name)
        first_contours = sides["intact"]["contours"]
        second_contours = sides["eroded"]["contours"]
        total_contours += len(first_contours)
        if len(first_contours) != len(second_contours):
            structure_mismatches.append(name)
            continue
        for index, (first, second) in enumerate(zip(first_contours, second_contours)):
            first_types = [point["segmentType"] for point in first["points"]]
            second_types = [point["segmentType"] for point in second["points"]]
            total_points += len(first_types)
            line_points += sum(segment_type == "line" for segment_type in first_types)
            off_curve_points += sum(segment_type is None for segment_type in first_types)
            if first_types != second_types or len(first_types) != len(second_types):
                structure_mismatches.append(f"{name}:{index}")
                continue
            if first["identifier"] != second["identifier"] or [
                point["identifier"] for point in first["points"]
            ] != [point["identifier"] for point in second["points"]]:
                identity_mismatches.append(f"{name}:{index}")
            first_positions = [point["position"] for point in first["points"]]
            second_positions = [point["position"] for point in second["points"]]
            if signed_area(first_positions) * signed_area(second_positions) <= 0:
                winding_mismatches.append(f"{name}:{index}")
            for position in POSITIONS:
                factor = position / 100.0
                interpolated = [
                    (
                        first_point[0] + (second_point[0] - first_point[0]) * factor,
                        first_point[1] + (second_point[1] - first_point[1]) * factor,
                    )
                    for first_point, second_point in zip(first_positions, second_positions)
                ]
                if abs(signed_area(interpolated)) <= 1e-6:
                    zero_areas += 1
                if not LinearRing(interpolated + interpolated[:1]).is_simple:
                    self_intersections += 1

    designspace = root / "artifacts" / "stage2-audit.designspace"
    build_dir = Path("/tmp/fracturize-phase-c-build")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    FontProject().run_from_designspace(
        designspace,
        output=("variable",),
        output_dir=build_dir,
        check_compatibility=True,
    )
    variable_font_path = next(build_dir.glob("*.ttf"))
    variable_font = TTFont(variable_font_path)
    try:
        tables = sorted(variable_font.keys())
        axis_tags = [axis.axisTag for axis in variable_font["fvar"].axes]
        glyph_order_count = len(variable_font.getGlyphOrder())
    finally:
        variable_font.close()

    pair_compatible = not any(
        (
            metadata_mismatches,
            structure_mismatches,
            identity_mismatches,
            winding_mismatches,
            self_intersections,
            zero_areas,
        )
    )
    report = {
        "auditPhase": "Prompt 2 Phase C re-validation",
        "projectSchemaAndIntegrityReopenPassed": True,
        "editedOutputs": project.edited_outputs,
        "motionAlgorithmVersion": project.data["motionPolicy"]["algorithmVersion"],
        "designspace": designspace.name,
        "fontmake": {
            "buildPassed": True,
            "temporaryVariableFont": str(variable_font_path),
            "axisTags": axis_tags,
            "glyphOrderCountIncludingNotdef": glyph_order_count,
            "tables": tables,
        },
        "serializedUFOCheck": {
            "reader": "fontTools.ufoLib.UFOReader",
            "glyphs": len(names),
            "glyphNames": names,
            "totalContours": total_contours,
            "totalPoints": total_points,
            "linePoints": line_points,
            "offCurvePoints": off_curve_points,
            "metadataMismatches": metadata_mismatches,
            "structureMismatches": structure_mismatches,
            "identityMismatches": identity_mismatches,
            "windingMismatches": winding_mismatches,
            "sampledPositions": list(POSITIONS),
            "interpolationSelfIntersections": self_intersections,
            "interpolationZeroArea": zero_areas,
            "pairCompatible": pair_compatible,
        },
    }
    write_json_report(report, root / "artifacts" / "stage2-phase-c-compatibility.json")
    if not pair_compatible:
        raise SystemExit("independent serialized pair validation failed")
    print(json.dumps({"glyphs": len(names), "pairCompatible": True, "variableBuild": True}, sort_keys=True))


if __name__ == "__main__":
    main()
