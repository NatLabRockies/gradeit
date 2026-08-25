from abc import ABCMeta, abstractmethod

from gradeit.coordinate import Coordinate


class ElevationModel(metaclass=ABCMeta):
    """Base class for models that look up elevation."""

    @abstractmethod
    def get_elevation(self, trace: list[Coordinate]) -> list[float]:
        """Return elevation in feet for the trace coordinates."""
