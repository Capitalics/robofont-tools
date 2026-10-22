from __future__ import annotations

from dataclasses import dataclass

from ..geometry import format_angle, format_number, measure_points


PLACEHOLDER = "—"


@dataclass(frozen=True)
class SelectedPointsPresentation:
    delta_x: str = PLACEHOLDER
    delta_y: str = PLACEHOLDER
    distance: str = PLACEHOLDER
    angle: str = PLACEHOLDER
    status: str = ""


def selected_contour_points(glyph) -> tuple:
    """Return selected on- and off-curve points, excluding other objects."""
    if glyph is None:
        return ()
    try:
        return tuple(
            point
            for contour in glyph.contours
            for point in contour.selectedPoints
        )
    except Exception:
        return ()


def presentation_for_glyph(glyph) -> SelectedPointsPresentation:
    """Create display-only state from selected contour points in a glyph."""
    points = selected_contour_points(glyph)
    if len(points) > 2:
        return SelectedPointsPresentation(status="Select exactly two points")
    if len(points) != 2:
        return SelectedPointsPresentation()

    first, second = points
    measurement = measure_points((first.x, first.y), (second.x, second.y))
    return SelectedPointsPresentation(
        delta_x=format_number(measurement.delta_x),
        delta_y=format_number(measurement.delta_y),
        distance=format_number(measurement.distance),
        angle=format_angle(measurement.angle),
    )
