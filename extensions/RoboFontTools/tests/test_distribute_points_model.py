from __future__ import annotations

import unittest

from robofont_tools.tools.distribute_points_model import (
    attached_offcurve_indices,
    even_distribution,
)


class EvenDistributionTests(unittest.TestCase):

    def test_already_evenly_spaced_values_are_unchanged(self):
        self.assertEqual(even_distribution([0, 50, 100]), (0, 50, 100))

    def test_middle_value_is_centred_between_the_extremes(self):
        self.assertEqual(even_distribution([0, 10, 100]), (0, 50, 100))

    def test_extremes_keep_their_original_values(self):
        result = even_distribution([13, 400, 87])
        self.assertEqual(result[0], 13)
        self.assertEqual(result[1], 400)

    def test_result_follows_input_order_not_sorted_order(self):
        # Input order A=10, B=95, C=40, D=200; ranked order is A, C, B, D.
        self.assertEqual(
            even_distribution([10, 95, 40, 200]), (10, 137, 73, 200)
        )

    def test_indivisible_span_is_rounded_to_integers(self):
        result = even_distribution([10, 73.33, 136.67, 200])
        self.assertEqual(result, (10, 73, 137, 200))
        for value in result:
            self.assertIsInstance(value, int)

    def test_negative_coordinates_are_distributed(self):
        self.assertEqual(even_distribution([-100, 0, 100]), (-100, 0, 100))
        self.assertEqual(even_distribution([-100, -90, 100]), (-100, 0, 100))

    def test_fewer_than_three_values_is_not_distributable(self):
        self.assertIsNone(even_distribution([]))
        self.assertIsNone(even_distribution([10]))
        self.assertIsNone(even_distribution([10, 200]))

    def test_zero_span_is_not_distributable(self):
        self.assertIsNone(even_distribution([40, 40, 40]))

    def test_tied_values_are_ranked_by_input_order(self):
        # The two 50s must keep their relative input order, so the first one
        # ranks lower and the same input always produces the same output.
        self.assertEqual(even_distribution([50, 50, 0, 90]), (30, 60, 0, 90))

    def test_five_values_are_evenly_spaced(self):
        self.assertEqual(
            even_distribution([0, 1, 2, 3, 400]), (0, 100, 200, 300, 400)
        )


class AttachedOffcurveTests(unittest.TestCase):

    CUBIC_CLOSED = ("curve", "offcurve", "offcurve", "curve",
                    "offcurve", "offcurve")

    def test_moving_oncurve_claims_both_of_its_cubic_handles(self):
        result = attached_offcurve_indices(self.CUBIC_CLOSED, {3}, closed=True)
        self.assertEqual(result, {2: 3, 4: 3})

    def test_first_point_of_a_closed_contour_wraps_around(self):
        result = attached_offcurve_indices(self.CUBIC_CLOSED, {0}, closed=True)
        self.assertEqual(result, {5: 0, 1: 0})

    def test_first_point_of_an_open_contour_does_not_wrap(self):
        types = ("move", "offcurve", "offcurve", "curve")
        result = attached_offcurve_indices(types, {0}, closed=False)
        self.assertEqual(result, {1: 0})

    def test_last_point_of_an_open_contour_does_not_wrap(self):
        types = ("move", "offcurve", "offcurve", "curve")
        result = attached_offcurve_indices(types, {3}, closed=False)
        self.assertEqual(result, {2: 3})

    def test_unselected_oncurve_points_claim_nothing(self):
        self.assertEqual(
            attached_offcurve_indices(self.CUBIC_CLOSED, set(), closed=True), {}
        )

    def test_quadratic_offcurve_between_two_moving_points_is_left_alone(self):
        types = ("qcurve", "offcurve", "qcurve")
        self.assertEqual(
            attached_offcurve_indices(types, {0, 2}, closed=False), {}
        )

    def test_quadratic_offcurve_follows_its_single_moving_neighbour(self):
        types = ("qcurve", "offcurve", "qcurve")
        self.assertEqual(
            attached_offcurve_indices(types, {0}, closed=False), {1: 0}
        )

    def test_line_points_have_no_handles(self):
        types = ("line", "line", "line")
        self.assertEqual(
            attached_offcurve_indices(types, {0, 1, 2}, closed=True), {}
        )

    def test_adjacent_moving_oncurve_points_claim_separate_handles(self):
        result = attached_offcurve_indices(
            self.CUBIC_CLOSED, {0, 3}, closed=True
        )
        self.assertEqual(result, {5: 0, 1: 0, 2: 3, 4: 3})


if __name__ == "__main__":
    unittest.main()
