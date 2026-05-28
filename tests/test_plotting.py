import unittest

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError
from gradeit.io import GradeResult

try:
    import folium  # noqa: F401

    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False


def _make_result(with_filtered: bool = False) -> GradeResult:
    coords = [
        Coordinate.from_lat_lon(39.0, -105.0),
        Coordinate.from_lat_lon(39.001, -105.001),
        Coordinate.from_lat_lon(39.002, -105.002),
        Coordinate.from_lat_lon(39.003, -105.003),
    ]
    elev = np.array([7000.0, 7010.0, 7030.0, 7020.0])
    dist = np.array([0.0, 500.0, 500.0, 500.0])
    grade = np.array([0.0, 0.02, 0.04, -0.02])
    filt_elev = elev if with_filtered else None
    filt_grade = grade * 0.5 if with_filtered else None
    return GradeResult(
        coordinates=coords,
        elevation_ft=elev,
        distances_ft=dist,
        grade_dec=grade,
        elevation_ft_filtered=filt_elev,
        grade_dec_filtered=filt_grade,
    )


@unittest.skipUnless(HAS_FOLIUM, "folium required for plotting tests")
class PlotGradeMapTest(unittest.TestCase):
    def test_returns_folium_map(self):
        from gradeit.plotting import plot_grade_map

        m = plot_grade_map(_make_result())
        self.assertIsInstance(m, folium.Map)

    def test_auto_single_layer_when_no_filter(self):
        # With no filtered profile, "auto" should not add a LayerControl.
        from gradeit.plotting import plot_grade_map

        m = plot_grade_map(_make_result(with_filtered=False))
        self.assertFalse(_has_layer_control(m))

    def test_auto_both_layers_when_filtered(self):
        # With a filtered profile, "auto" should expose both as a toggle.
        from gradeit.plotting import plot_grade_map

        m = plot_grade_map(_make_result(with_filtered=True))
        self.assertTrue(_has_layer_control(m))
        names = _feature_group_names(m)
        self.assertIn("Filtered grade", names)
        self.assertIn("Raw grade", names)

    def test_filtered_without_filter_raises(self):
        from gradeit.plotting import plot_grade_map

        with self.assertRaises(InvalidInputError):
            plot_grade_map(_make_result(with_filtered=False), grade="filtered")

    def test_both_without_filter_raises(self):
        from gradeit.plotting import plot_grade_map

        with self.assertRaises(InvalidInputError):
            plot_grade_map(_make_result(with_filtered=False), grade="both")

    def test_invalid_grade_choice_raises(self):
        from gradeit.plotting import plot_grade_map

        with self.assertRaises(InvalidInputError):
            plot_grade_map(_make_result(), grade="nope")  # type: ignore[arg-type]

    def test_invalid_range_raises(self):
        from gradeit.plotting import plot_grade_map

        with self.assertRaises(InvalidInputError):
            plot_grade_map(_make_result(), grade_range_pct=(5.0, 5.0))

    def test_too_few_coordinates_raises(self):
        from gradeit.plotting import plot_grade_map

        result = GradeResult(
            coordinates=[Coordinate.from_lat_lon(39.0, -105.0)],
            elevation_ft=np.array([7000.0]),
            distances_ft=np.array([0.0]),
            grade_dec=np.array([0.0]),
        )
        with self.assertRaises(InvalidInputError):
            plot_grade_map(result)

    def test_method_on_result_delegates(self):
        m = _make_result().plot_map()
        self.assertIsInstance(m, folium.Map)

    def test_tooltip_includes_segment_index(self):
        # Hover tooltip must expose the array index for cross-referencing
        # against result.grade_dec / .elevation_ft / .coordinates.
        from gradeit.plotting import plot_grade_map

        m = plot_grade_map(_make_result())
        html = m._repr_html_()
        # For 4 coords there are 3 segments (i=1..3); every index should appear.
        for i in (1, 2, 3):
            self.assertIn(f"index: {i}", html)

    def test_nonfinite_grade_does_not_raise(self):
        # A NaN grade should fall through to a neutral color rather than crash.
        from gradeit.plotting import plot_grade_map

        result = _make_result()
        result.grade_dec[1] = np.nan
        m = plot_grade_map(result)
        self.assertIsInstance(m, folium.Map)


def _has_layer_control(m: "folium.Map") -> bool:
    return any(child.__class__.__name__ == "LayerControl" for child in m._children.values())


def _feature_group_names(m: "folium.Map") -> set:
    return {
        getattr(child, "layer_name", None)
        for child in m._children.values()
        if child.__class__.__name__ == "FeatureGroup"
    }


if __name__ == "__main__":
    unittest.main()
