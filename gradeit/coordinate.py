from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A WGS84-style latitude/longitude point.

    Stores latitude and longitude as floats.
    """

    latitude: float
    longitude: float

    @classmethod
    def from_lat_lon(cls, latitude: float, longitude: float) -> Coordinate:
        """Create a Coordinate from a latitude and longitude."""
        return cls(latitude=float(latitude), longitude=float(longitude))
