from math import asin, cos, radians, sin, sqrt
from typing import List

import numpy as np

from gradeit.coordinate import Coordinate


def get_grade(
    elevation_profile: List[float],
    distances: List[float],
    min_distance_ft: float = 1.0,
) -> List[float]:
    """Compute decimal road grade (rise/run) for an elevation profile.

    Grade is the point-to-point ratio ``Δelevation / distance``. Segments shorter than
    ``min_distance_ft`` are treated as undefined -- near-coincident coordinates
    otherwise divide a small elevation change by a near-zero distance and yield physically impossible grades.
    Undefined segments carry the previous valid grade forward.

    Parameters
    ----------
    elevation_profile : List[float]
        Elevation at each point (n > 1).
    distances : List[float]
        Horizontal distance of each segment, length len(elevation_profile) - 1.
    min_distance_ft : float, optional
        Segments shorter than this are undefined and carry the previous grade,
        by default 1.0. Raise it to also suppress noise-driven spikes at crawl speed.
    """
    # check that n > 1
    if len(elevation_profile) < 2:
        raise ValueError(
            "Determining grade requires at least 2 coordinates\n\t\ti.e. Input size of n > 1"
        )

    d_elev = np.diff(np.asarray(elevation_profile, dtype=float))
    dist_arr = np.asarray(distances, dtype=float)

    # only divide where the segment is long enough to define a grade; sub-threshold
    # segments stay NaN and are carried-forward below (no divide-by-zero warning)
    grade = np.full(d_elev.shape, np.nan)
    measurable = dist_arr >= min_distance_ft
    grade[measurable] = d_elev[measurable] / dist_arr[measurable]

    grade = np.insert(grade, 0, 0.0)
    grade = np.round(grade, decimals=4)
    for a in range(len(grade) - 1):
        if np.isinf(grade[a + 1]) or np.isnan(grade[a + 1]):
            grade[a + 1] = grade[a]

    return list(grade)


def get_distances(coordinates: List[Coordinate]) -> List[float]:
    """
    Compute the distance between each coordinate pair
    """
    FT_PER_KM = 3280.84
    # place a zero up front
    distances = []
    i = 1
    while i < len(coordinates):
        dist_ft = haversine(coordinates[i - 1], coordinates[i]) * FT_PER_KM
        distances += [dist_ft]
        i += 1

    return distances


def haversine(coord1: Coordinate, coord2: Coordinate, get_bearing: bool = False) -> float:
    """
    Calculates the great circle distance and bearing (if requested)
    between two points on the earth's surface

    Parameters:
        coord1: a Coordinate object
        coord2: a Coordinate object

    Returns:
        distance: the great circle distance in km

    """
    # convert decimal to radians
    lat1 = radians(coord1.latitude)
    lon1 = radians(coord1.longitude)
    lat2 = radians(coord2.latitude)
    lon2 = radians(coord2.longitude)

    # compute haversine result
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    R = 6371  # radius of earth in km
    distance = c * R
    # round to centimeter precision
    distance = round(distance, 5)

    return distance
