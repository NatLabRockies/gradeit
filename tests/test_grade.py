import unittest
import warnings

import numpy as np
import pandas as pd

from gradeit import grade
from gradeit.coordinate import Coordinate


class GradeTest(unittest.TestCase):
    def setUp(self):
        self.lat1 = 39.702730
        self.lat2 = 39.695368
        self.lon1 = -105.245678
        self.lon2 = -105.209049

        self.coord1 = Coordinate.from_lat_lon(self.lat1, self.lon1)
        self.coord2 = Coordinate.from_lat_lon(self.lat2, self.lon2)

        self.expected_dist_km = 3.665130
        self.expected_bearing_deg = 104.63

        self.data = pd.DataFrame()
        self.data["lat"] = np.linspace(39.702730, 39.695368, 10)
        self.data["lon"] = np.linspace(-105.245678, -105.209049, 10)

        self.data["elev_ft"] = np.array(
            [
                7048.15,
                7015.69,
                7157.89,
                7004.84,
                6921.27,
                6840.03,
                6696.7,
                6735.26,
                6554.42,
                6445.5,
            ]
        )

        self.data["dist_ft"] = [
            0,
            1336.0892816,
            1336.0892816,
            1336.0892816,
            1336.0892816,
            1336.12209,
            1336.12209,
            1336.12209,
            1336.12209,
            1336.1548984,
        ]

        self.data["grade_dec"] = [
            0.0,
            -0.0243,
            0.1064,
            -0.1146,
            -0.0625,
            -0.0608,
            -0.1073,
            0.0289,
            -0.1353,
            -0.0815,
        ]

    def test_haversine(self):
        dist = grade.haversine(self.coord1, self.coord2)

        self.assertEqual(dist, self.expected_dist_km)

    def test_get_distances(self):
        coordinates = [
            Coordinate.from_lat_lon(lat, lon)
            for lat, lon in zip(self.data.lat.values, self.data.lon.values)
        ]
        dist_arr = grade.get_distances(coordinates)

        np.testing.assert_array_equal(dist_arr, np.array(self.data.dist_ft[1:]))

    def test_get_grade_from_distance(self):
        coordinates = [
            Coordinate.from_lat_lon(lat, lon)
            for lat, lon in zip(self.data.lat.values, self.data.lon.values)
        ]
        dist_arr = grade.get_distances(coordinates)
        grade_arr = grade.get_grade(self.data.elev_ft, distances=dist_arr)

        np.testing.assert_array_equal(dist_arr, self.data.dist_ft[1:])
        np.testing.assert_array_equal(grade_arr, self.data.grade_dec)

    def test_get_grade_zero_distance(self):
        # a zero-distance segment (coincident points) carries the previous grade
        # instead of producing inf
        grade_arr = grade.get_grade([5000.0, 5005.0, 5006.0], distances=[100.0, 0.0])

        self.assertEqual(grade_arr, [0.0, 0.05, 0.05])
        self.assertFalse(any(np.isinf(g) or np.isnan(g) for g in grade_arr))

    def test_get_grade_zero_distance_no_warning(self):
        # the old implementation emitted a divide-by-zero RuntimeWarning here
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            grade.get_grade([5000.0, 5005.0, 5006.0], distances=[100.0, 0.0])

    def test_get_grade_tiny_distance(self):
        # a sub-foot elevation change over a sub-foot distance no longer blows up;
        # the old behavior returned 0.5 / 0.3 = 1.6667 (167% grade)
        grade_arr = grade.get_grade([5000.0, 5005.0, 5005.5], distances=[100.0, 0.3])

        self.assertEqual(grade_arr, [0.0, 0.05, 0.05])

    def test_get_grade_bounded_stationary_stretch(self):
        # a profile that stops/crawls in the middle stays bounded and finite
        elev = [5000.0, 5001.0, 5001.2, 5001.2, 5001.3, 5006.0]
        dist = [50.0, 0.2, 0.0, 0.1, 50.0]
        grade_arr = grade.get_grade(elev, distances=dist)

        self.assertTrue(all(abs(g) < 1.0 for g in grade_arr))
        self.assertFalse(any(np.isnan(g) or np.isinf(g) for g in grade_arr))

    def test_get_grade_first_segment_undefined(self):
        # a sub-threshold first segment carries the leading zero
        grade_arr = grade.get_grade([5000.0, 5000.1], distances=[0.2])

        self.assertEqual(grade_arr, [0.0, 0.0])

    def test_get_grade_min_distance_param(self):
        # the threshold is configurable: a 100 ft segment is undefined under a 200 ft
        # threshold and carries the leading zero
        grade_arr = grade.get_grade([5000.0, 5050.0], distances=[100.0], min_distance_ft=200.0)

        self.assertEqual(grade_arr, [0.0, 0.0])


if __name__ == "__main__":
    unittest.main(warnings="ignore")
