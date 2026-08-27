from abc import ABCMeta, abstractmethod

from gradeit.coordinate import Coordinate


class ElevationFilter(metaclass=ABCMeta):
    """Base class for elevation-profile filters."""

    @abstractmethod
    def filter(self, elevation_profile: list[float], coordinates: list[Coordinate]) -> list[float]:
        """Return a filtered elevation profile in feet."""
