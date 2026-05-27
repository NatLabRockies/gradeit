import unittest

import numpy as np

from gradeit.filters import BridgeGradeFilter, GradeFilter


def _uniform_distances(n: int, step_ft: float) -> np.ndarray:
    """Distance array with a leading 0, so cumulative distance is i * step_ft."""
    d = np.full(n, step_ft, dtype=float)
    d[0] = 0.0
    return d


class BridgeGradeFilterTest(unittest.TestCase):
    def test_is_a_grade_filter(self):
        self.assertIsInstance(BridgeGradeFilter(), GradeFilter)

    def test_zeros_a_real_bridge_span(self):
        # A dip: steep down, a long flat span (the bare-earth valley floor),
        # then steep up, on a gently-rolling road. The far field has a small but
        # non-zero grade so it is not itself detected as flat.
        n = 40
        step = 50.0  # ft between points
        grade = np.full(n, 0.01)  # gentle baseline (above the flat threshold)
        grade[5:9] = -0.10  # steep descent into the valley
        grade[9:31] = 0.0  # flat valley floor (the spurious "bridge")
        grade[31:35] = 0.10  # steep climb out

        f = BridgeGradeFilter(
            extension_ft=200.0, min_bridge_len_ft=100.0, edge_grade_threshold=0.05
        )
        out = f.filter(grade, _uniform_distances(n, step))

        # The flat valley floor is flattened to exactly zero.
        self.assertTrue(np.allclose(out[9:31], 0.0))
        # Far-away points (well outside the extended window) are untouched.
        self.assertEqual(out[0], grade[0])
        self.assertEqual(out[-1], grade[-1])

    def test_short_flat_span_is_not_a_bridge(self):
        # A flat span shorter than min_bridge_len_ft must be left alone, even
        # though it sits between steep sections.
        n = 20
        step = 50.0
        grade = np.full(n, 0.08)
        grade[9:11] = 0.0  # only ~50 ft of flat -> below min_bridge_len

        f = BridgeGradeFilter(min_bridge_len_ft=500.0)
        out = f.filter(grade, _uniform_distances(n, step))
        np.testing.assert_array_equal(out, grade)

    def test_flat_road_without_dip_is_not_a_bridge(self):
        # A long flat span with no steep shoulders anywhere nearby is an ordinary
        # flat road, not a valley-spanning bridge: the edge-grade gate keeps it.
        n = 40
        step = 50.0
        grade = np.zeros(n)
        grade[5:35] = 0.0  # long flat, gentle surroundings (all < edge threshold)
        grade[:5] = 0.01
        grade[35:] = 0.01

        f = BridgeGradeFilter(min_bridge_len_ft=100.0, edge_grade_threshold=0.05)
        out = f.filter(grade, _uniform_distances(n, step))
        np.testing.assert_array_equal(out, grade)

    def test_does_not_mutate_input(self):
        n = 40
        step = 50.0
        grade = np.zeros(n)
        grade[5:9] = -0.10
        grade[31:35] = 0.10
        original = grade.copy()

        BridgeGradeFilter(extension_ft=200.0).filter(grade, _uniform_distances(n, step))
        np.testing.assert_array_equal(grade, original)

    def test_accepts_python_lists(self):
        n = 40
        grade = [0.0] * n
        for i in range(5, 9):
            grade[i] = -0.1
        for i in range(31, 35):
            grade[i] = 0.1
        distances = [50.0] * n
        distances[0] = 0.0

        out = BridgeGradeFilter(extension_ft=200.0).filter(grade, distances)
        self.assertIsInstance(out, np.ndarray)
        self.assertEqual(out.shape, (n,))


if __name__ == "__main__":
    unittest.main()
