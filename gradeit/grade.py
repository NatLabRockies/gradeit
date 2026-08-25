from math import asin, cos, radians, sin, sqrt

import numpy as np

from gradeit.coordinate import Coordinate


def get_grade(
    elevation_profile: list[float],
    distances: list[float],
    min_distance_ft: float = 1.0,
) -> list[float]:
    """Compute decimal road grade (rise/run) for an elevation profile.

    Grade is ``elevation change / distance`` between points. Segments shorter
    than ``min_distance_ft`` use the previous valid grade.

    Parameters
    ----------
    elevation_profile : List[float]
        Elevation at each point (n > 1).
    distances : List[float]
        Horizontal distance of each segment, length len(elevation_profile) - 1.
    min_distance_ft : float, optional
        Segments shorter than this use the previous grade. Default: 1.0.
    """
    # Grade needs at least two points.
    if len(elevation_profile) < 2:
        raise ValueError(
            "Determining grade requires at least 2 coordinates\n\t\ti.e. Input size of n > 1"
        )

    d_elev = np.diff(np.asarray(elevation_profile, dtype=float))
    dist_arr = np.asarray(distances, dtype=float)

    # Divide only segments that are long enough to measure.
    grade = np.full(d_elev.shape, np.nan)
    measurable = dist_arr >= min_distance_ft
    grade[measurable] = d_elev[measurable] / dist_arr[measurable]

    grade = np.insert(grade, 0, 0.0)
    grade = np.round(grade, decimals=4)
    for a in range(len(grade) - 1):
        if np.isinf(grade[a + 1]) or np.isnan(grade[a + 1]):
            grade[a + 1] = grade[a]

    return list(grade)


def get_distances(coordinates: list[Coordinate]) -> list[float]:
    """Return the distance in feet between each pair of nearby coordinates."""
    FT_PER_KM = 3280.84
    distances = []
    i = 1
    while i < len(coordinates):
        dist_ft = haversine(coordinates[i - 1], coordinates[i]) * FT_PER_KM
        distances += [dist_ft]
        i += 1

    return distances


def haversine(coord1: Coordinate, coord2: Coordinate, get_bearing: bool = False) -> float:
    """Return the great-circle distance in kilometers between two coordinates."""
    # Convert degrees to radians.
    lat1 = radians(coord1.latitude)
    lon1 = radians(coord1.longitude)
    lat2 = radians(coord2.latitude)
    lon2 = radians(coord2.longitude)

    # Calculate the great-circle distance.
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    R = 6371  # Earth radius in kilometers.
    distance = c * R
    # Round to centimeter precision.
    distance = round(distance, 5)

    return distance
