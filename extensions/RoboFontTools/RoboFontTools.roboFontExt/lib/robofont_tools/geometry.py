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


def measure_points(first: Point, second: Point) -> PointMeasurement:
    """Measure from ``first`` to ``second``, in the order given.

    This is the one measuring rule. Deltas are signed and the angle runs
    from -180 to 180 degrees, so callers pass points in outline order.
    """
    vector_x = float(second[0]) - float(first[0])
    vector_y = float(second[1]) - float(first[1])
    return PointMeasurement(
        delta_x=vector_x,
        delta_y=vector_y,
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
