from __future__ import annotations

import unittest
from dataclasses import dataclass

from robofont_tools.tools.selected_points_model import presentation_for_glyph


@dataclass
class FakePoint:
    x: float
    y: float
    selected: bool = True
    point_type: str = "line"


class FakeContour:
    def __init__(self, points):
        self.points = tuple(points)

    @property
    def selectedPoints(self):
        return tuple(point for point in self.points if point.selected)


class FakeGlyph:
    def __init__(self, contours):
        self.contours = tuple(contours)


class SelectedPointsPresentationTests(unittest.TestCase):

    def test_no_glyph_and_one_point_use_neutral_placeholders(self):
        for glyph in (
            None,
            FakeGlyph([FakeContour([FakePoint(10, 20)])]),
        ):
            with self.subTest(glyph=glyph):
                presentation = presentation_for_glyph(glyph)
                self.assertEqual(presentation.delta_x, "—")
                self.assertEqual(presentation.delta_y, "—")
                self.assertEqual(presentation.distance, "—")
                self.assertEqual(presentation.angle, "—")
                self.assertEqual(presentation.status, "")

    def test_more_than_two_points_shows_message(self):
        glyph = FakeGlyph(
            [
                FakeContour(
                    [
                        FakePoint(0, 0),
                        FakePoint(10, 0),
                        FakePoint(20, 0),
                    ]
                )
            ]
        )
        presentation = presentation_for_glyph(glyph)
        self.assertEqual(presentation.delta_x, "—")
        self.assertEqual(presentation.status, "Select exactly two points")

    def test_selected_points_can_span_contours_and_include_off_curves(self):
        first = FakePoint(0, 0, selected=True, point_type="offcurve")
        second = FakePoint(30, 40)
        glyph = FakeGlyph(
            [
                FakeContour(
                    [
                        first,
                        FakePoint(10, 10, selected=False),
                    ]
                ),
                FakeContour([second]),
            ]
        )
        presentation = presentation_for_glyph(glyph)
        self.assertEqual(presentation.delta_x, "30")
        self.assertEqual(presentation.delta_y, "40")
        self.assertEqual(presentation.distance, "50")
        self.assertEqual(presentation.angle, "53.13°")
        self.assertEqual(presentation.status, "")
        self.assertEqual((first.x, first.y, first.selected), (0, 0, True))
        self.assertEqual((second.x, second.y, second.selected), (30, 40, True))

    def test_presentation_preserves_the_selected_point_direction(self):
        glyph = FakeGlyph([FakeContour([FakePoint(30, 40), FakePoint(0, 0)])])
        presentation = presentation_for_glyph(glyph)
        self.assertEqual(presentation.delta_x, "-30")
        self.assertEqual(presentation.delta_y, "-40")
        self.assertEqual(presentation.distance, "50")
        self.assertEqual(presentation.angle, "-126.87°")


if __name__ == "__main__":
    unittest.main()
