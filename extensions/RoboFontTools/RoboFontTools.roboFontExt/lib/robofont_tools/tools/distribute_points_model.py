"""Pure distribution maths for Distribute Points.

Nothing here imports RoboFont, so the whole calculation is covered by the
headless test suite.
"""
from __future__ import annotations

from math import floor
from typing import Collection, Sequence

OFFCURVE = "offcurve"


def _round_half_up(value: float) -> int:
    """Round to the nearest integer, resolving .5 upwards.

    Python's built-in ``round`` is half-to-even, which makes an evenly
    distributed run of points drift in ways a designer cannot predict.
    """
    return floor(float(value) + 0.5)


def even_distribution(values: Sequence[float]) -> tuple[float, ...] | None:
    """Space ``values`` evenly between their own extremes.

    The result follows the input order, so callers can zip it straight back
    onto the objects they collected. The lowest and highest values are
    returned untouched; every value in between is rounded to an integer.

    Returns ``None`` when the operation is meaningless: fewer than three
    values, or every value already identical.
    """
    numbers = [float(value) for value in values]
    count = len(numbers)
    if count < 3:
        return None

    # The index tiebreak keeps points that share a coordinate in their input
    # order, so the same selection always produces the same result.
    ranking = sorted(range(count), key=lambda index: (numbers[index], index))
    lowest = numbers[ranking[0]]
    highest = numbers[ranking[-1]]
    if highest == lowest:
        return None

    step = (highest - lowest) / (count - 1)
    result: list[float] = [0.0] * count
    for rank, index in enumerate(ranking):
        if rank == 0 or rank == count - 1:
            result[index] = values[index]
        else:
            result[index] = _round_half_up(lowest + rank * step)
    return tuple(result)


def attached_offcurve_indices(
    point_types: Sequence[str],
    moving: Collection[int],
    closed: bool,
) -> dict[int, int]:
    """Map each off-curve point to the moving on-curve point it follows.

    An off-curve point follows a neighbour only when exactly one of its
    adjacent on-curve points is moving. A quadratic off-curve sitting between
    two moving on-curve points is left alone rather than guessed at.
    """
    moving = set(moving)
    count = len(point_types)
    followers: dict[int, int] = {}
    if not moving or count == 0:
        return followers

    for index, point_type in enumerate(point_types):
        if point_type != OFFCURVE:
            continue
        owners = [
            neighbour
            for neighbour in _neighbours(index, count, closed)
            if point_types[neighbour] != OFFCURVE and neighbour in moving
        ]
        if len(owners) == 1:
            followers[index] = owners[0]
    return followers


def _neighbours(index: int, count: int, closed: bool) -> tuple[int, ...]:
    """Return the adjacent indices, wrapping only on a closed contour."""
    previous = index - 1
    following = index + 1
    if closed:
        return (previous % count, following % count)
    return tuple(
        neighbour
        for neighbour in (previous, following)
        if 0 <= neighbour < count
    )
