"""Paired, separated rough edges for a straight slice. No RoboFont imports."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, ceil
from random import Random


@dataclass(frozen=True)
class SliceSettings:
    spacing: float = 25.0
    gap: float = 20.0
    jitter: float = 30.0

    def validate(self):
        if not 5 <= self.spacing <= 50:
            raise ValueError("point spacing must be between 5 and 50 units")
        if self.gap <= 0 or self.jitter < 0:
            raise ValueError("gap must be positive and jitter cannot be negative")


def paired_edges(start, end, side_signs, settings, rng=None):
    """Return two polylines, indexed by the original contour's side of the cut.

    Both edges use the same tangential stations and center displacement. Their
    independent roughness only moves *away* from the center, so every pair of
    corresponding segments stays at least ``gap`` apart.
    """
    settings.validate()
    if set(side_signs) != {-1, 1}:
        raise ValueError("the two contours must be on opposite sides")
    length = hypot(end[0] - start[0], end[1] - start[1])
    if length < 2:
        raise ValueError("slice is too short")
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    nx, ny = -uy, ux
    intervals = max(1, round(length / settings.spacing))
    step = length / intervals
    rng = rng or Random()
    result = {1: [], -1: []}
    for index in range(intervals + 1):
        interior = 0 < index < intervals
        tangent = index * step
        if interior:
            tangent += rng.uniform(-min(step * .2, settings.jitter), min(step * .2, settings.jitter))
        # Keep endpoints on their original slice station. The center wiggle is
        # shared; each edge gets additional outward motion of its own.
        center = rng.uniform(-settings.jitter * .65, settings.jitter * .65) if interior else 0
        for side in (-1, 1):
            outward = rng.uniform(0, settings.jitter * .35) if interior else 0
            normal = center + side * (settings.gap / 2 + outward)
            result[side].append((start[0] + ux*tangent + nx*normal,
                                 start[1] + uy*tangent + ny*normal))
    return result
