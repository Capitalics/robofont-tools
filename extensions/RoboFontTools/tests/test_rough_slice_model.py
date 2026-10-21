from __future__ import annotations

import random
import unittest
from math import hypot

from robofont_tools.tools.rough_slice_model import SliceSettings, paired_edges


class RoughSliceModelTests(unittest.TestCase):
    def test_every_station_and_segment_has_an_open_gap(self):
        settings = SliceSettings(spacing=25, gap=20, jitter=30)
        for seed in range(100):
            edges = paired_edges((10, 20), (130, 105), (-1, 1), settings,
                                 random.Random(seed))
            self.assertEqual(len(edges[-1]), len(edges[1]))
            self.assertGreaterEqual(len(edges[1]), 6)
            dx, dy = 120, 85
            length = hypot(dx, dy)
            nx, ny = -dy / length, dx / length
            ux, uy = dx / length, dy / length
            previous = None
            for left, right in zip(edges[1], edges[-1]):
                separation = (left[0]-right[0])*nx + (left[1]-right[1])*ny
                self.assertGreaterEqual(separation, 20 - 1e-9)
                station = (left[0]-10)*ux + (left[1]-20)*uy
                self.assertAlmostEqual(station, (right[0]-10)*ux + (right[1]-20)*uy)
                if previous is not None:
                    self.assertGreater(station, previous)
                previous = station

    def test_invalid_spacing_and_gap(self):
        for settings in (SliceSettings(spacing=4), SliceSettings(spacing=51),
                         SliceSettings(gap=0), SliceSettings(jitter=-1)):
            with self.assertRaises(ValueError):
                settings.validate()


if __name__ == "__main__":
    unittest.main()
