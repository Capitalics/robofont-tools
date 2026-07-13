from __future__ import annotations

from shapely import set_precision
from shapely.geometry import LinearRing

from .geometry import interpolate_contours, master_contours_to_union, signed_area
from .model import (
    MasterGlyph,
    ReconstructionMetrics,
    ValidationFinding,
    ValidationReport,
)

SAMPLED_POSITIONS = (0, 10, 25, 50, 75, 90, 100)
MAX_NORMALIZED_SYMMETRIC_DIFFERENCE = 1e-8
MAX_HAUSDORFF_UPM_RATIO = 1e-7
RECONSTRUCTION_PRECISION_UPM_RATIO = 1e-12


def validate_pair(*, source_silhouette, intact: MasterGlyph, eroded: MasterGlyph, units_per_em, minimum_area):
    findings: list[ValidationFinding] = []
    if intact.name != eroded.name:
        findings.append(ValidationFinding("hard_error", "glyph_name", "glyph names differ"))
    if intact.width != eroded.width:
        findings.append(ValidationFinding("hard_error", "width", "glyph widths differ"))
    if len(intact.contours) != len(eroded.contours):
        findings.append(ValidationFinding("hard_error", "contour_count", "contour counts differ"))

    for index, (first, second) in enumerate(zip(intact.contours, eroded.contours)):
        if first.identifier != second.identifier or first.fragment_id != second.fragment_id:
            findings.append(ValidationFinding("hard_error", "identity", f"identity differs at contour {index}"))
        if first.point_ids != second.point_ids:
            findings.append(ValidationFinding("hard_error", "point_identity", f"point IDs differ at contour {index}"))
        if len(first.points) != len(second.points):
            findings.append(ValidationFinding("hard_error", "point_count", f"point count differs at contour {index}"))
        if first.is_hole != second.is_hole:
            findings.append(ValidationFinding("hard_error", "winding_role", f"hole role differs at contour {index}"))
        if signed_area(first.points) * signed_area(second.points) <= 0:
            findings.append(ValidationFinding("hard_error", "winding", f"winding changed at contour {index}"))

    intact_union = master_contours_to_union(intact.contours)
    # GEOS may retain zero-width internal seams after polygonizing coincident
    # fragment edges. Compare on a declared UPM-relative precision grid so
    # those numerical seams do not masquerade as visible boundary error.
    precision_grid = units_per_em * RECONSTRUCTION_PRECISION_UPM_RATIO
    measured_source = set_precision(source_silhouette, precision_grid)
    measured_intact = set_precision(intact_union, precision_grid)
    symmetric_difference = measured_source.symmetric_difference(measured_intact).area
    normalized_difference = symmetric_difference / measured_source.area
    hausdorff = measured_source.boundary.hausdorff_distance(measured_intact.boundary)
    reconstruction = ReconstructionMetrics(
        source_area=measured_source.area,
        intact_area=measured_intact.area,
        symmetric_difference_area=symmetric_difference,
        normalized_symmetric_difference=normalized_difference,
        hausdorff_distance=hausdorff,
    )
    if normalized_difference > MAX_NORMALIZED_SYMMETRIC_DIFFERENCE:
        findings.append(
            ValidationFinding(
                "hard_error",
                "reconstruction_area",
                f"normalized symmetric difference {normalized_difference:.3g} exceeds {MAX_NORMALIZED_SYMMETRIC_DIFFERENCE:.3g}",
            )
        )
    if hausdorff > units_per_em * MAX_HAUSDORFF_UPM_RATIO:
        findings.append(
            ValidationFinding(
                "hard_error",
                "reconstruction_boundary",
                f"Hausdorff distance {hausdorff:.3g} exceeds {units_per_em * MAX_HAUSDORFF_UPM_RATIO:.3g}",
            )
        )

    area_floor = max(minimum_area * 0.01, units_per_em * units_per_em * 1e-9)
    for position in SAMPLED_POSITIONS:
        contours = interpolate_contours(intact.contours, eroded.contours, position / 100.0)
        for index, contour in enumerate(contours):
            area = abs(signed_area(contour.points))
            if area <= area_floor:
                findings.append(
                    ValidationFinding(
                        "interpolation_risk",
                        "near_zero_area",
                        f"contour {index} has area {area:.3g} at {position}%",
                    )
                )
            ring = LinearRing(list(contour.points) + [contour.points[0]])
            if not ring.is_simple:
                findings.append(
                    ValidationFinding(
                        "interpolation_risk",
                        "self_intersection",
                        f"contour {index} self-intersects at {position}%",
                    )
                )

    # Geometry/identity errors and objective interpolation risks both block a
    # generated pair. Subjective visual warnings remain advisory.
    compatible = not any(
        finding.level in {"hard_error", "interpolation_risk"}
        for finding in findings
    )
    return ValidationReport(
        compatible=compatible,
        reconstruction=reconstruction,
        findings=tuple(findings),
        sampled_positions=SAMPLED_POSITIONS,
    )
