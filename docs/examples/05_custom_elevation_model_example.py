"""
# Bringing Your Own Elevation Source

Use this interface when your elevation data comes from a source gradeit does
not know about: a different national DEM, a lidar survey, a database, a
vendor API, or synthetic terrain in a test.
"""


def main():
    import math

    from gradeit import Coordinate, ElevationModel

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

        def get_elevation(self, trace: list[Coordinate]) -> list[float]:
            out = []
            for coord in trace:
                d_lat = coord.latitude - self.center.latitude
                d_lon = coord.longitude - self.center.longitude
                r2 = (d_lat**2 + d_lon**2) / self.width_deg**2
                base = 5000.0 + 1000.0 * d_lon  # a gentle eastward tilt
                out.append(base + self.peak_ft * math.exp(-r2))
            return out


if __name__ == "__main__":
    main()
