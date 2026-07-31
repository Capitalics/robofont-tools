from __future__ import annotations

import unittest

from robofont_tools.tools.contour_probe_model import (
    OutlineCache,
    cache_from_contours,
    measure_contour_probe,
    nearest_contour_distance,
)


class FakePoint:
    def __init__(self, x, y, point_type):
        self.x = x
        self.y = y
        self.type = point_type


class FakeSegment:
    def __init__(self, segment_type, points):
        self.type = segment_type
        self.points = tuple(points)
        self.onCurve = self.points[-1] if points and points[-1].type != "offcurve" else None
        self.offCurve = self.points if self.onCurve is None else self.points[:-1]


class FakeContour:
    open = False

    def __init__(self, segments):
        self.segments = tuple(segments)


class ContourProbeModelTests(unittest.TestCase):
    def test_measures_a_rectangle_across_its_filled_interval(self):
        edges = (((0., 0.), (100., 0.)), ((100., 0.), (100., 200.)), ((100., 200.), (0., 200.)), ((0., 200.), (0., 0.)))
        result = measure_contour_probe(OutlineCache((), edges), (2., 100.))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.thickness, 100.)
        self.assertEqual(result.intersection_a, (0., 100.))
        self.assertEqual(result.intersection_b, (100., 100.))
        self.assertEqual(result.tangent[0], 0.)
        self.assertAlmostEqual(abs(result.normal[0]), 1.)
        self.assertEqual(result.normal[1], 0.)

    def test_measures_a_rectangle_vertically_at_its_top_edge(self):
        edges = (
            ((0., 0.), (100., 0.)), ((100., 0.), (100., 200.)),
            ((100., 200.), (0., 200.)), ((0., 200.), (0., 0.)),
        )
        result = measure_contour_probe(OutlineCache((), edges), (50., 198.))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.thickness, 200.)
        self.assertAlmostEqual(abs(result.normal[1]), 1.)
        self.assertEqual(result.normal[0], 0.)

    def test_returns_no_result_without_outline_edges(self):
        self.assertIsNone(measure_contour_probe(OutlineCache((), ()), (0., 0.)))

    def test_reports_nearest_outline_distance_for_diagnostics(self):
        cache = OutlineCache((), (((0., 0.), (100., 0.)),))
        self.assertEqual(nearest_contour_distance(cache, (50., 20.)), 20.)

    def test_builds_edges_from_fontparts_style_line_segments(self):
        points = [
            FakePoint(0, 0, "line"), FakePoint(100, 0, "line"),
            FakePoint(100, 200, "line"), FakePoint(0, 200, "line"),
        ]
        cache = cache_from_contours([
            FakeContour([FakeSegment("line", [point]) for point in points])
        ])
        self.assertEqual(len(cache.edges), 4)
        self.assertEqual(measure_contour_probe(cache, (2, 100)).thickness, 100)

    def test_counter_is_primary_and_adjacent_stem_is_secondary(self):
        # Outer counter-clockwise contour and inner clockwise counter.
        edges = (
            ((0., 0.), (100., 0.)), ((100., 0.), (100., 100.)),
            ((100., 100.), (0., 100.)), ((0., 100.), (0., 0.)),
            ((30., 30.), (30., 70.)), ((30., 70.), (70., 70.)),
            ((70., 70.), (70., 30.)), ((70., 30.), (30., 30.)),
        )
        result = measure_contour_probe(OutlineCache((), edges), (50., 50.))
        self.assertIsNotNone(result)
        self.assertFalse(result.primary.is_filled)
        self.assertEqual(result.primary.thickness, 40.)
        self.assertIsNotNone(result.secondary)
        self.assertTrue(result.secondary.is_filled)
        self.assertEqual(result.secondary.thickness, 30.)

    def test_stem_is_primary_and_adjacent_counter_is_secondary(self):
        edges = (
            ((0., 0.), (100., 0.)), ((100., 0.), (100., 100.)),
            ((100., 100.), (0., 100.)), ((0., 100.), (0., 0.)),
            ((30., 30.), (30., 70.)), ((30., 70.), (70., 70.)),
            ((70., 70.), (70., 30.)), ((70., 30.), (30., 30.)),
        )
        result = measure_contour_probe(OutlineCache((), edges), (15., 50.))
        self.assertIsNotNone(result)
        self.assertTrue(result.primary.is_filled)
        self.assertEqual(result.primary.thickness, 30.)
        self.assertIsNotNone(result.secondary)
        self.assertFalse(result.secondary.is_filled)
        self.assertEqual(result.secondary.thickness, 40.)
