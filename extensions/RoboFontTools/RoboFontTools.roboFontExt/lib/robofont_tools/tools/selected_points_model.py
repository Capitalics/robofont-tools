from __future__ import annotations

from dataclasses import dataclass

from math import atan2, degrees, hypot

from ..geometry import format_angle, format_number


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
    delta_x = float(second.x) - float(first.x)
    delta_y = float(second.y) - float(first.y)
    distance = hypot(delta_x, delta_y)
    angle = degrees(atan2(delta_y, delta_x))
    return SelectedPointsPresentation(
        delta_x=format_number(delta_x),
        delta_y=format_number(delta_y),
        distance=format_number(distance),
        angle=format_angle(angle),
    )
