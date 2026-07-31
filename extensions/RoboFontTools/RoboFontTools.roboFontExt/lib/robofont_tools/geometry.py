from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import TypeAlias


Point: TypeAlias = tuple[float, float]


@dataclass(frozen=True)
class PointMeasurement:
    delta_x: float
    delta_y: float
    distance: float
    angle: float


def order_points(point_1: Point, point_2: Point) -> tuple[Point, Point]:
    """Order points left-to-right, then bottom-to-top for equal x values."""
    first = (float(point_1[0]), float(point_1[1]))
    second = (float(point_2[0]), float(point_2[1]))
    if (second[0], second[1]) < (first[0], first[1]):
        first, second = second, first
    return first, second


def measure_points(point_1: Point, point_2: Point) -> PointMeasurement:
    """Measure two points without modifying either input."""
    first, second = order_points(point_1, point_2)
    vector_x = second[0] - first[0]
    vector_y = second[1] - first[1]
    return PointMeasurement(
        delta_x=abs(vector_x),
        delta_y=abs(vector_y),
        distance=hypot(vector_x, vector_y),
        angle=degrees(atan2(vector_y, vector_x)),
    )


def format_number(value: float) -> str:
    """Format a measurement with at most two fractional digits."""
    numeric = float(value)
    if numeric == 0:
        numeric = 0.0
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.2f}".rstrip("0").rstrip(".")


def format_angle(value: float) -> str:
    return f"{format_number(value)}°"
