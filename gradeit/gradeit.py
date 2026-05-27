from pathlib import Path
from typing import Optional, Union
import pandas as pd
from gradeit.elevation.elevation_model import ElevationModel

from gradeit.elevation.filters import SavitzkyGolayFilter
from gradeit.elevation.usgs_local import USGSLocal
from gradeit.elevation.usgs_api import USGSApi
from gradeit.coordinate import Coordinate
from gradeit.grade import get_distances, get_grade


def gradeit(
    df: pd.DataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    filtering: bool = False,
    source: str = "usgs-api",
    usgs_db_path: Optional[Union[str, Path]] = None,
    des_sg: int = 17,
    sampling: str = "bilinear",
) -> pd.DataFrame:
    """
    Add grade to an input dataframe with latitude and longitude columns

    Parameters
    ----------
    df : pd.DataFrame
        dataframe with latitude and longitude columns
    lat_col : str, optional
        name of the latitude column, by default "latitude"
    lon_col : str, optional
        name of the longitude column, by default "longitude"
    filtering : bool, optional
        whether to filter the elevation data, by default False
    source : str, optional
        data source for elevation data, by default "usgs-api"
    usgs_db_path : Optional[Union[str, Path]], optional
        path to local USGS raster tiles, by default None
    des_sg : int, optional
        Savitzky-Golay filter window size, by default 17
    sampling : str, optional
        DEM sampling mode for the "usgs-local" source: "bilinear" (default)
        or "nearest". Ignored by the "usgs-api" source.

    Returns
    -------
    pd.DataFrame
        dataframe with grade columns appended
    """
    lats = df[lat_col].values
    lons = df[lon_col].values

    coordinates = [Coordinate.from_lat_lon(lat, lon) for lat, lon in zip(lats, lons)]

    emodel: ElevationModel

    # Run the appropriate elevation function based on user's desired data source
    if source == "usgs-api":
        emodel = USGSApi()
    elif source == "usgs-local":
        if usgs_db_path is None:
            raise Exception(
                "You must provide a path to the local USGS raster tiles if you want"
                "to use the 'usgs-local' option"
            )
        usgs_db_path = Path(usgs_db_path)
        emodel = USGSLocal(usgs_db_path, sampling=sampling)
    else:
        raise Exception(
            "Invalid elevation data source. Provide one of these options: ['usgs-api','usgs-local']"
        )

    elevation_ft = emodel.get_elevation(coordinates)
    df["elevation_ft"] = elevation_ft

    distances_ft = get_distances(coordinates)
    df["distances_ft"] = [0] + distances_ft

    grade_dec_unfiltered = get_grade(elevation_ft, distances=distances_ft)
    df["grade_dec_unfiltered"] = grade_dec_unfiltered

    if filtering:
        efilter = SavitzkyGolayFilter(window=des_sg)
        elevation_ft_filtered = efilter.filter(elevation_ft, coordinates)
        df["elevation_ft_filtered"] = elevation_ft_filtered
        grade_dec_filtered = get_grade(elevation_ft_filtered, distances=distances_ft)
        df["grade_dec_filtered"] = grade_dec_filtered

    return df
