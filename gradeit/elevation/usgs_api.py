from typing import List


from gradeit.coordinate import Coordinate
from gradeit.elevation.elevation_model import ElevationModel


URL = "https://epqs.nationalmap.gov/v1/"
UNITS = "feet"
OUTPUT = "json"


def usgs_query_call(coord: Coordinate) -> float:
    """
    Build and run the query to the USGS API endpoint
    """
    try:
        import requests
        from requests import JSONDecodeError
    except ImportError as e:
        raise ImportError(
            "The 'requests' library is required to use the USGS API elevation source. "
            "Please install it with 'pip install gradeit[api]'."
        ) from e

    lat = str(coord.latitude)
    lon = str(coord.longitude)

    query = f"{URL}{OUTPUT}?x={lon}&y={lat}&units={UNITS}&wkid=4326&includeDate=False"
    response = requests.get(query)
    try:
        result = response.json()
    except JSONDecodeError:
        raise Exception(f"Error when querying USGS API: {response.text}")

    try:
        raw_elevation = result["value"]
    except KeyError:
        raise Exception("Error when querying USGS API: elevation not present in result")
    try:
        elev = float(raw_elevation)
    except ValueError as e:
        raise ValueError(
            f"Error when querying USGS API: elevation is not a number: {raw_elevation}"
        ) from e

    return elev


class USGSApi(ElevationModel):
    """
    An elevation model to look up elevation by latitude, longitude
    coordinates. The source for the data is the public USGS API, which compiles
    and serves data from the 1/3 arc-second Digital Elevation Model.

    More information is available at https://nationalmap.gov/epqs/
    """

    def get_elevation(self, trace: List[Coordinate]) -> List[float]:
        elevations = list(map(usgs_query_call, trace))
        return elevations
