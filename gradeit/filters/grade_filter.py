from abc import ABCMeta, abstractmethod
from typing import List, Optional

import numpy as np

from gradeit.coordinate import Coordinate


class GradeFilter(metaclass=ABCMeta):
    """Abstract class for grade filters.

    A grade filter post-processes a computed grade profile (e.g. to correct
    bridges and overpasses the bare-earth DEM does not represent). This is
    distinct from an :class:`~gradeit.filters.elevation_filter.ElevationFilter`,
    which smooths the *elevation* profile **before** grade is computed; a grade
    filter operates on the grade **after** it is computed.
    """

    @abstractmethod
    def filter(
        self,
        grade: np.ndarray,
        distances_ft: np.ndarray,
        coordinates: List[Coordinate],
        elevation_ft: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Return a corrected decimal-grade profile.

        Parameters
        ----------
        grade:
            Decimal grade at each point (length ``n``).
        distances_ft:
            Per-segment horizontal distance in feet, with a leading ``0`` so it
            aligns with ``grade`` (length ``n``).
        coordinates:
            The trace coordinates (length ``n``).
        elevation_ft:
            The elevation profile the grade was derived from, if a filter needs
            it. May be ``None``.
        """
        ...
