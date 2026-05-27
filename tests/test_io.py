import unittest

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError, MissingDependencyError
from gradeit.io import GradeResult, to_coordinates

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class ToCoordinatesTest(unittest.TestCase):
    def setUp(self):
        self.lats = [39.0, 39.1, 39.2]
        self.lons = [-105.0, -105.1, -105.2]
        self.expected = [Coordinate.from_lat_lon(la, lo) for la, lo in zip(self.lats, self.lons)]

    def test_numpy_n_by_2(self):
        arr = np.column_stack([self.lats, self.lons])
        self.assertEqual(to_coordinates(arr), self.expected)

    def test_numpy_wrong_shape_raises(self):
        with self.assertRaises(InvalidInputError):
            to_coordinates(np.zeros((3, 3)))
        with self.assertRaises(InvalidInputError):
            to_coordinates(np.zeros(3))

    def test_mapping(self):
        data = {"latitude": self.lats, "longitude": self.lons}
        self.assertEqual(to_coordinates(data), self.expected)

    def test_mapping_custom_columns(self):
        data = {"lat": self.lats, "lon": self.lons}
        self.assertEqual(to_coordinates(data, lat_col="lat", lon_col="lon"), self.expected)

    def test_mapping_missing_column_raises(self):
        with self.assertRaises(InvalidInputError):
            to_coordinates({"latitude": self.lats})

    def test_list_of_tuples(self):
        data = list(zip(self.lats, self.lons))
        self.assertEqual(to_coordinates(data), self.expected)

    def test_list_of_coordinates_passes_through(self):
        self.assertEqual(to_coordinates(self.expected), self.expected)

    def test_bad_iterable_item_raises(self):
        with self.assertRaises(InvalidInputError):
            to_coordinates([(39.0, -105.0), (1.0, 2.0, 3.0)])

    def test_unsupported_type_raises(self):
        with self.assertRaises(InvalidInputError):
            to_coordinates(42)

    @unittest.skipUnless(HAS_PANDAS, "pandas required")
    def test_dataframe(self):
        df = pd.DataFrame({"latitude": self.lats, "longitude": self.lons})
        self.assertEqual(to_coordinates(df), self.expected)

    @unittest.skipUnless(HAS_PANDAS, "pandas required")
    def test_dataframe_custom_columns(self):
        df = pd.DataFrame({"y": self.lats, "x": self.lons})
        self.assertEqual(to_coordinates(df, lat_col="y", lon_col="x"), self.expected)


class GradeResultTest(unittest.TestCase):
    def setUp(self):
        self.coords = [Coordinate.from_lat_lon(39.0, -105.0), Coordinate.from_lat_lon(39.1, -105.1)]
        self.elev = np.array([7000.0, 7010.0])
        self.dist = np.array([0.0, 100.0])
        self.grade = np.array([0.0, 0.1])

    def test_to_dict_unfiltered_keys(self):
        result = GradeResult(self.coords, self.elev, self.dist, self.grade)
        d = result.to_dict()
        self.assertEqual(
            set(d),
            {"latitude", "longitude", "elevation_ft", "distances_ft", "grade_dec_unfiltered"},
        )
        self.assertEqual(d["grade_dec_unfiltered"], [0.0, 0.1])

    def test_to_dict_filtered_keys(self):
        result = GradeResult(
            self.coords,
            self.elev,
            self.dist,
            self.grade,
            elevation_ft_filtered=self.elev,
            grade_dec_filtered=self.grade,
        )
        d = result.to_dict()
        self.assertIn("elevation_ft_filtered", d)
        self.assertIn("grade_dec_filtered", d)

    @unittest.skipUnless(HAS_PANDAS, "pandas required")
    def test_to_dataframe_columns(self):
        result = GradeResult(self.coords, self.elev, self.dist, self.grade)
        df = result.to_dataframe()
        self.assertEqual(
            list(df.columns),
            ["latitude", "longitude", "elevation_ft", "distances_ft", "grade_dec_unfiltered"],
        )
        self.assertEqual(len(df), 2)

    @unittest.skipIf(HAS_PANDAS, "exercises the missing-pandas path")
    def test_to_dataframe_without_pandas_raises(self):
        result = GradeResult(self.coords, self.elev, self.dist, self.grade)
        with self.assertRaises(MissingDependencyError):
            result.to_dataframe()


if __name__ == "__main__":
    unittest.main()
