from abc import ABCMeta, abstractmethod
from typing import List


from gradeit.coordinate import Coordinate


class ElevationFilter(metaclass=ABCMeta):
    """Base class for elevation-profile filters."""

    @abstractmethod
    def filter(self, elevation_profile: List[float], coordinates: List[Coordinate]) -> List[float]:
        """Return a filtered elevation profile in feet."""
        pass
