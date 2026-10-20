"""Selection-only contour path logic, independent of RoboFont imports."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot


def _path(start: int, end: int, count: int) -> tuple[int, ...]:
    """Walk forward through contour point order, including both endpoints."""
    result = [start]
    while result[-1] != end:
        result.append((result[-1] + 1) % count)
    return tuple(result)


def _length(points: tuple, path: tuple[int, ...]) -> float:
    return sum(
        hypot(points[b].x - points[a].x, points[b].y - points[a].y)
        for a, b in zip(path, path[1:])
    )


def routes(points: tuple, first: int, second: int, closed: bool):
    """Return the shorter and alternate point-index paths.

    Length follows the contour's ordered points, including off-curve handles.
    An open contour has just one path. Equal lengths prefer fewer points, then
    increasing point order, making the first click deterministic.
    """
    if first > second:
        first, second = second, first
    if not closed:
        return tuple(range(first, second + 1)), None
    forward = _path(first, second, len(points))
    backward = _path(second, first, len(points))
    if (_length(points, backward), len(backward)) < (
        _length(points, forward), len(forward)
    ):
        return backward, forward
    return forward, backward


@dataclass
class _LastSelection:
    glyph_token: object
    contour_index: int
    outline: tuple
    selected: tuple[int, ...]
    alternate: tuple[int, ...]


class SelectBetweenState:
    """Remember one action so a repeated click can flip a closed contour."""

    def __init__(self):
        self.last: _LastSelection | None = None

    def clear(self):
        self.last = None

    def select(self, glyph) -> bool:
        """Select a route, returning whether a valid action was available."""
        if glyph is None:
            self.clear()
            return False

        contours = tuple(glyph.contours)
        selected = [
            (contour_index, point_index)
            for contour_index, contour in enumerate(contours)
            for point_index, point in enumerate(contour.points)
            if point.selected
        ]
        token = glyph.naked() if hasattr(glyph, "naked") else glyph

        last = self.last
        if last is not None and token is last.glyph_token:
            index = last.contour_index
            if index < len(contours):
                contour = contours[index]
                points = tuple(contour.points)
                outline = tuple((p.x, p.y, p.type) for p in points)
                if (
                    not contour.open
                    and outline == last.outline
                    and set(selected)
                    == {(index, point_index) for point_index in last.selected}
                ):
                    alternate = last.alternate
                    # RoboFont 4.6's bundled FontParts documents index input,
                    # but its index normalizer is missing. Point objects work.
                    contour.selectedPoints = [points[i] for i in alternate]
                    self.last = _LastSelection(
                        token, index, outline, alternate, last.selected,
                    )
                    return True

        self.clear()
        if len(selected) != 2 or selected[0][0] != selected[1][0]:
            return False

        index = selected[0][0]
        contour = contours[index]
        points = tuple(contour.points)
        chosen, alternate = routes(
            points, selected[0][1], selected[1][1], not contour.open
        )
        contour.selectedPoints = [points[i] for i in chosen]
        if alternate is not None:
            outline = tuple((p.x, p.y, p.type) for p in points)
            self.last = _LastSelection(
                token, index, outline, chosen, alternate
            )
        return True
