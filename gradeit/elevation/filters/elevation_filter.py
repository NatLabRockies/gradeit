from abc import ABCMeta, abstractmethod
from typing import List


from gradeit.coordinate import Coordinate


class ElevationFilter(metaclass=ABCMeta):
    """
    Abstract class for elevation-profile filters
    """

    @abstractmethod
    def filter(self, elevation_profile: List[float], coordinates: List[Coordinate]) -> List[float]:
        """
        Smooth an elevation profile (in feet) for a list of points in a trace
        """
        pass
