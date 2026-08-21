"""
# Bringing Your Own Elevation Source

gradeit includes two elevation models: `USGSApi` and `USGSLocal`. Neither
model has special status. The `elevation_model` parameter accepts any object
that implements the `ElevationModel` interface, which has a single method.

Use this interface when your elevation data comes from a source gradeit does
not know about: a different national DEM, a lidar survey, a database, a
vendor API, or synthetic terrain in a test.

This page needs no data files and no network connection.
"""


def main():
    import math
    from typing import List

    import numpy as np

    from gradeit import Coordinate, ElevationModel, gradeit

    """
    ## The interface

    `ElevationModel` is an abstract base class with one abstract method:

    ```python
    class ElevationModel(metaclass=ABCMeta):
        @abstractmethod
        def get_elevation(self, trace: List[Coordinate]) -> List[float]:
            ...
    ```

    The contract is small but strict:

    - **Input** is a list of `Coordinate` objects. These are frozen
      dataclasses with `.latitude` and `.longitude` attributes, in decimal
      degrees.
    - **Output** is elevation in **feet**, one value per input coordinate, in
      the same order. gradeit does not convert units for you. If your source
      reports meters, convert the values before you return them.
    - **Unknown elevation is `float("nan")`**. It is not `None`, and it is
      not a sentinel value like `-9999`. Both built-in models return `NaN`
      for points outside their coverage, and the filters expect this value.

    ## A synthetic model

    Here is a complete implementation. It places a hill on the landscape as
    a Gaussian bump. This gives a smooth profile with a known shape, which
    is useful for testing filters against a signal whose true shape you
    already know.
    """

    class SyntheticTerrain(ElevationModel):
        """Analytic terrain: a Gaussian hill on a tilted plane."""

        def __init__(self, center: Coordinate, peak_ft: float = 350.0, width_deg: float = 0.02):
            self.center = center
            self.peak_ft = peak_ft
            self.width_deg = width_deg

        def get_elevation(self, trace: List[Coordinate]) -> List[float]:
            out = []
            for coord in trace:
                d_lat = coord.latitude - self.center.latitude
                d_lon = coord.longitude - self.center.longitude
                r2 = (d_lat**2 + d_lon**2) / self.width_deg**2
                base = 5000.0 + 1000.0 * d_lon  # a gentle eastward tilt
                out.append(base + self.peak_ft * math.exp(-r2))
            return out

    """
    That is all it takes. Now drive a straight west-to-east trace over the
    hill:
    """

    center = Coordinate.from_lat_lon(39.75, -105.2)
    trace = [(39.75, -105.2 + 0.0004 * i) for i in range(-60, 61)]

    result = gradeit(trace, elevation_model=SyntheticTerrain(center))

    peak = int(np.argmax(result.elevation_ft))
    print(f"{len(trace)} points, {result.distances_ft.sum() / 5280:.2f} miles")
    print(f"peak at index {peak}: {result.elevation_ft[peak]:.1f} ft")
    print(f"elevation range: {result.elevation_ft.min():.1f} to {result.elevation_ft.max():.1f} ft")
    print(
        f"max |grade|: raw {100 * np.abs(result.grade_dec).max():.2f}%, "
        f"filtered {100 * np.abs(result.grade_dec_filtered).max():.2f}%"
    )

    """
    This terrain is smooth and noise-free, so filtration has almost nothing
    to remove. This is exactly the sanity check you want: a filter that
    changes clean input in a meaningful way will also distort real terrain.
    """

    drift = np.abs(result.elevation_ft_filtered - result.elevation_ft)
    print(f"median |filtered - raw|: {np.median(drift):.3f} ft")
    print(f"max    |filtered - raw|: {drift.max():.3f} ft")

    """
    ## Reporting gaps in coverage

    Return `NaN` where you have no data. This model refuses to answer
    outside a bounding box, the same way `USGSLocal` returns `NaN` outside
    its tiles.
    """

    class BoundedTerrain(ElevationModel):
        """Wraps another model, returning NaN outside a lat/lon box."""

        def __init__(self, inner: ElevationModel, min_lon: float, max_lon: float):
            self.inner = inner
            self.min_lon = min_lon
            self.max_lon = max_lon

        def get_elevation(self, trace: List[Coordinate]) -> List[float]:
            values = self.inner.get_elevation(trace)
            return [
                value if self.min_lon <= coord.longitude <= self.max_lon else float("nan")
                for coord, value in zip(trace, values)
            ]

    bounded = gradeit(
        trace,
        elevation_model=BoundedTerrain(SyntheticTerrain(center), -105.21, -105.19),
        elevation_filter=None,
    )
    covered = np.isfinite(bounded.elevation_ft)
    print(
        f"{covered.sum()} of {len(trace)} points inside coverage, {(~covered).sum()} returned NaN"
    )

    """
    ## Caching an expensive source

    The interface has only one method, so wrapping it is easy. If your real
    source makes a slow network call — `USGSApi` sends one HTTP request *per
    point* — a cache is worth adding, especially when several traces revisit
    the same roads.
    """

    class CachedElevation(ElevationModel):
        """Memoizes lookups by rounded coordinate."""

        def __init__(self, inner: ElevationModel, ndigits: int = 6):
            self.inner = inner
            self.ndigits = ndigits
            self._cache: dict = {}
            self.lookups = 0

        def get_elevation(self, trace: List[Coordinate]) -> List[float]:
            def key(c: Coordinate):
                return (round(c.latitude, self.ndigits), round(c.longitude, self.ndigits))

            missing = [c for c in trace if key(c) not in self._cache]
            if missing:
                self.lookups += len(missing)
                for coord, value in zip(missing, self.inner.get_elevation(missing)):
                    self._cache[key(coord)] = value
            return [self._cache[key(c)] for c in trace]

    cached = CachedElevation(SyntheticTerrain(center))
    gradeit(trace, elevation_model=cached)
    print(f"first pass:  {cached.lookups} underlying lookups")
    gradeit(trace, elevation_model=cached)
    print(f"second pass: {cached.lookups} underlying lookups (unchanged — all cached)")

    """
    ```{note}
    The cache key rounds coordinates, so points closer together than the
    rounding distance share the same answer. At six decimal places, this
    distance is about four inches. This is well below the DEM's ~33 ft post
    spacing, so it cannot change a result.
    ```

    ## Where to go next

    See [Elevation Data](../elevation_data) for the two built-in models and
    steps to obtain the real USGS tiles. See [Concepts](../concepts) for the
    rest of the interfaces gradeit exposes.
    """


if __name__ == "__main__":
    main()
