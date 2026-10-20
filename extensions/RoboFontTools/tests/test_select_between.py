from __future__ import annotations

import unittest
from dataclasses import dataclass

from robofont_tools.tools.select_between_model import SelectBetweenState, routes


@dataclass
class Point:
    x: float
    y: float
    type: str = "line"
    selected: bool = False


class Contour:
    def __init__(self, points, open=False):
        self.points = tuple(points)
        self.open = open

    @property
    def selectedPoints(self):
        return tuple(point for point in self.points if point.selected)

    @selectedPoints.setter
    def selectedPoints(self, points):
        if any(isinstance(point, int) for point in points):
            raise TypeError("This RoboFont version requires point objects")
        for point in self.points:
            point.selected = any(point is selected for selected in points)


class Glyph:
    def __init__(self, contours):
        self.contours = tuple(contours)

    def naked(self):
        return self


def selected_indices(contour):
    return {index for index, point in enumerate(contour.points) if point.selected}


class SelectBetweenTests(unittest.TestCase):
    def test_closed_contour_shorter_route_then_opposite_then_shorter(self):
        contour = Contour([
            Point(0, 0, selected=True), Point(10, 0), Point(20, 0),
            Point(30, 0, selected=True), Point(30, 100), Point(0, 100),
        ])
        state = SelectBetweenState()
        glyph = Glyph([contour])
        for expected in ({0, 1, 2, 3}, {0, 3, 4, 5}, {0, 1, 2, 3}):
            self.assertTrue(state.select(glyph))
            self.assertEqual(selected_indices(contour), expected)

    def test_offcurve_handles_are_included(self):
        contour = Contour([
            Point(0, 0, selected=True),
            Point(10, 20, "offcurve"), Point(20, 20, "offcurve"),
            Point(30, 0, "curve", True),
        ], open=True)
        self.assertTrue(SelectBetweenState().select(Glyph([contour])))
        self.assertEqual(selected_indices(contour), {0, 1, 2, 3})

    def test_open_contour_selects_only_interval(self):
        contour = Contour([
            Point(0, 0), Point(10, 0, selected=True),
            Point(20, 0), Point(30, 0, selected=True), Point(40, 0),
        ], open=True)
        state = SelectBetweenState()
        glyph = Glyph([contour])
        self.assertTrue(state.select(glyph))
        self.assertEqual(selected_indices(contour), {1, 2, 3})
        self.assertFalse(state.select(glyph))  # no second path on an open contour
        self.assertEqual(selected_indices(contour), {1, 2, 3})

    def test_different_contours_leave_selection_untouched(self):
        first = Contour([Point(0, 0, selected=True), Point(10, 0)])
        second = Contour([Point(20, 0, selected=True), Point(30, 0)])
        self.assertFalse(SelectBetweenState().select(Glyph([first, second])))
        self.assertEqual(selected_indices(first), {0})
        self.assertEqual(selected_indices(second), {0})

    def test_changed_selection_starts_a_new_action(self):
        contour = Contour([
            Point(0, 0, selected=True), Point(10, 0), Point(20, 0),
            Point(30, 0, selected=True), Point(30, 100), Point(0, 100),
        ])
        state = SelectBetweenState()
        glyph = Glyph([contour])
        self.assertTrue(state.select(glyph))
        contour.selectedPoints = [contour.points[1], contour.points[4]]
        self.assertTrue(state.select(glyph))
        self.assertEqual(selected_indices(contour), {1, 2, 3, 4})

    def test_changed_outline_does_not_flip_stale_route(self):
        contour = Contour([
            Point(0, 0, selected=True), Point(10, 0), Point(20, 0),
            Point(30, 0, selected=True), Point(30, 100), Point(0, 100),
        ])
        state = SelectBetweenState()
        glyph = Glyph([contour])
        self.assertTrue(state.select(glyph))
        contour.points[1].x = 11
        self.assertFalse(state.select(glyph))
        self.assertEqual(selected_indices(contour), {0, 1, 2, 3})

    def test_fewer_or_more_than_two_points_do_nothing(self):
        contour = Contour([
            Point(0, 0, selected=True), Point(10, 0), Point(20, 0)
        ])
        glyph = Glyph([contour])
        state = SelectBetweenState()
        self.assertFalse(state.select(glyph))
        contour.points[1].selected = True
        self.assertTrue(state.select(glyph))
        contour.selectedPoints = list(contour.points)
        self.assertFalse(state.select(glyph))
        self.assertEqual(selected_indices(contour), {0, 1, 2})

    def test_route_length_uses_geometry_and_tie_is_deterministic(self):
        points = tuple(Point(x, y) for x, y in [
            (0, 0), (1, 0), (2, 0), (100, 0), (100, 100), (0, 100)
        ])
        short, other = routes(points, 0, 3, True)
        self.assertEqual(short, (0, 1, 2, 3))
        self.assertEqual(other, (3, 4, 5, 0))
        square = tuple(Point(x, y) for x, y in [
            (0, 0), (10, 0), (10, 10), (0, 10)
        ])
        self.assertEqual(routes(square, 0, 2, True)[0], (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
