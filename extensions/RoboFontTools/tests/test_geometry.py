from __future__ import annotations

import math
import unittest

from robofont_tools.geometry import format_angle, format_number, measure_points


class GeometryTests(unittest.TestCase):

    def test_horizontal_points(self):
        measurement = measure_points((10, 20), (60, 20))
        self.assertEqual(measurement.delta_x, 50)
        self.assertEqual(measurement.delta_y, 0)
        self.assertEqual(measurement.distance, 50)
        self.assertEqual(measurement.angle, 0)

    def test_vertical_points_are_ordered_bottom_to_top(self):
        measurement = measure_points((10, 80), (10, 20))
        self.assertEqual(measurement.delta_x, 0)
        self.assertEqual(measurement.delta_y, 60)
        self.assertEqual(measurement.distance, 60)
        self.assertEqual(measurement.angle, 90)

    def test_diagonal_points(self):
        measurement = measure_points((0, 0), (3, 4))
        self.assertEqual(measurement.delta_x, 3)
        self.assertEqual(measurement.delta_y, 4)
        self.assertEqual(measurement.distance, 5)
        self.assertAlmostEqual(
            measurement.angle,
            math.degrees(math.atan2(4, 3)),
        )

    def test_reversed_input_has_the_same_deterministic_measurement(self):
        forward = measure_points((10, 30), (40, 5))
        reversed_input = measure_points((40, 5), (10, 30))
        self.assertEqual(reversed_input, forward)
        self.assertLess(forward.angle, 0)

    def test_coincident_points(self):
        measurement = measure_points((12.5, -3), (12.5, -3))
        self.assertEqual(measurement.delta_x, 0)
        self.assertEqual(measurement.delta_y, 0)
        self.assertEqual(measurement.distance, 0)
        self.assertEqual(measurement.angle, 0)

    def test_integer_formatting(self):
        cases = (
            (0, "0"),
            (-0.0, "0"),
            (12, "12"),
            (12.0, "12"),
            (-7.0, "-7"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_number(value), expected)

    def test_fractional_formatting(self):
        cases = (
            (1.5, "1.5"),
            (1.234, "1.23"),
            (1.236, "1.24"),
            (-3.125, "-3.12"),
            (45.5, "45.5"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_number(value), expected)

    def test_angle_formatting_uses_degree_symbol(self):
        self.assertEqual(format_angle(53.130102), "53.13°")


if __name__ == "__main__":
    unittest.main()
