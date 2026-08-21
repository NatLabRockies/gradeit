"""Online elevation lookup against the USGS 3DEP service.

Points are sampled in batches through the 3DEP ImageServer's ``getSamples``
operation rather than one request per point. The values are identical to the
Elevation Point Query Service (EPQS) -- EPQS is a single-point wrapper over
this same dynamic mosaic -- but a whole trace costs a handful of requests
instead of one per coordinate.
"""

import json
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.elevation.elevation_model import ElevationModel
from gradeit.exceptions import ElevationLookupError, MissingDependencyError

URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples"

# getSamples silently truncates to its own sample limit -- a request for 2,000
# points comes back as locationId 0..999 with HTTP 200 and no error -- and that
# limit is *not* the service's advertised maxRecordCount (2000). Chunking at the
# real limit is what keeps the truncation from ever happening.
MAX_POINTS_PER_REQUEST = 1000

# The service reports elevation in meters; gradeit works in feet.
_FT_PER_M = 3.28084

_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_RETRIES = 3
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _require_requests():
    try:
        import requests
    except ImportError as e:
        raise MissingDependencyError(
            "The 'requests' library is required to use the USGS API elevation source. "
            "It is a core dependency of gradeit; reinstall the package with "
            "'pip install gradeit' to pull it in."
        ) from e
    return requests


class USGSApi(ElevationModel):
    """
    An elevation model to look up elevation by latitude, longitude
    coordinates. The source for the data is the public USGS 3D Elevation
    Program (3DEP) bare-earth service, the same dynamic mosaic that backs the
    Elevation Point Query Service.

    Coordinates are sent in batches of up to :data:`MAX_POINTS_PER_REQUEST`,
    so a trace costs ``ceil(n / 1000)`` requests rather than ``n``.

    Points outside the service's coverage return ``NaN``, matching
    :class:`~gradeit.elevation.USGSLocal`.

    Parameters
    ----------
    batch_size:
        Points per request. Capped at :data:`MAX_POINTS_PER_REQUEST`, above
        which the service truncates the response without reporting an error.
    sampling:
        ``"nearest"`` (default) returns the containing cell, which reproduces
        the Elevation Point Query Service exactly. ``"bilinear"`` asks the
        service to interpolate the surrounding cells, matching the default of
        :class:`~gradeit.elevation.USGSLocal`.
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Attempts per batch on timeout, connection error, or a retryable status
        (429/5xx). Backs off between attempts.

    More information is available at https://www.usgs.gov/3d-elevation-program
    """

    # ArcGIS resampling method names for the `interpolation` parameter. Omitting
    # the parameter also yields nearest-neighbor, but naming it is explicit.
    _INTERPOLATION = {
        "nearest": "RSP_NearestNeighbor",
        "bilinear": "RSP_BilinearInterpolation",
    }

    def __init__(
        self,
        batch_size: int = MAX_POINTS_PER_REQUEST,
        sampling: str = "nearest",
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")
        if sampling not in self._INTERPOLATION:
            raise ValueError(
                f"sampling must be one of {sorted(self._INTERPOLATION)}, got {sampling!r}."
            )
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")
        self.batch_size = min(batch_size, MAX_POINTS_PER_REQUEST)
        self.sampling = sampling
        self.timeout = timeout
        self.max_retries = max_retries

    def get_elevation(self, trace: List[Coordinate]) -> List[float]:
        if not trace:
            return []

        requests = _require_requests()
        elevation_ft = np.full(len(trace), np.nan, dtype=np.float64)

        # One session for the whole trace so the TLS handshake and connection
        # are reused across batches.
        with requests.Session() as session:
            for start in range(0, len(trace), self.batch_size):
                chunk = trace[start : start + self.batch_size]
                samples = self._query_batch(session, chunk)
                for location_id, meters in samples.items():
                    elevation_ft[start + location_id] = meters * _FT_PER_M

        return elevation_ft.tolist()

    def _query_batch(self, session, chunk: Sequence[Coordinate]) -> Dict[int, float]:
        """Sample one batch, returned as ``{index within chunk: meters}``.

        Points the service has no data for are absent from the mapping rather
        than present as ``None``; the caller leaves those as ``NaN``.
        """
        payload = self._build_payload(chunk)
        result = self._post_with_retry(session, payload, len(chunk))

        # ArcGIS reports failures in a 200 body, so an HTTP-level check is not
        # enough to know the request succeeded.
        if "error" in result:
            error = result["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            raise ElevationLookupError(f"Error when querying USGS 3DEP service: {message}")

        raw_samples = result.get("samples")
        if raw_samples is None:
            raise ElevationLookupError(
                "Error when querying USGS 3DEP service: no samples present in result"
            )

        samples: Dict[int, float] = {}
        for sample in raw_samples:
            # Samples come back unordered and out-of-coverage points are dropped
            # entirely, so position in the response says nothing about which
            # input point it belongs to -- only locationId does.
            location_id = self._parse_location_id(sample, len(chunk))
            value = self._parse_value(sample)
            if value is not None:
                samples[location_id] = value
        return samples

    def _build_payload(self, chunk: Sequence[Coordinate]) -> Dict[str, str]:
        geometry = {
            "points": [[coord.longitude, coord.latitude] for coord in chunk],
            "spatialReference": {"wkid": 4326},
        }
        return {
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryMultipoint",
            "returnFirstValueOnly": "true",
            "interpolation": self._INTERPOLATION[self.sampling],
            "f": "json",
        }

    def _post_with_retry(self, session, payload: Dict[str, str], n_points: int) -> Dict[str, Any]:
        """POST one batch, retrying transient failures.

        POST rather than GET because a full batch of coordinates overflows
        practical URL length limits.
        """
        requests = _require_requests()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            if attempt:
                # Bounded linear backoff; the service is a shared public
                # resource, so back off rather than hammering it.
                time.sleep(min(2.0 * attempt, 10.0))
            try:
                response = session.post(URL, data=payload, timeout=self.timeout)
            except requests.RequestException as e:
                last_error = e
                continue

            if response.status_code in _RETRY_STATUSES:
                last_error = ElevationLookupError(
                    f"USGS 3DEP service returned HTTP {response.status_code}"
                )
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as e:
                raise ElevationLookupError(
                    f"Error when querying USGS 3DEP service: HTTP {response.status_code}"
                ) from e

            try:
                result = response.json()
            except ValueError as e:
                raise ElevationLookupError(
                    f"Error when querying USGS 3DEP service: {response.text[:500]}"
                ) from e

            if not isinstance(result, dict):
                raise ElevationLookupError(
                    "Error when querying USGS 3DEP service: unexpected response shape"
                )
            return result

        raise ElevationLookupError(
            f"Error when querying USGS 3DEP service for {n_points} points after "
            f"{self.max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _parse_location_id(sample: Any, n_points: int) -> int:
        if not isinstance(sample, dict):
            raise ElevationLookupError(
                "Error when querying USGS 3DEP service: malformed sample in result"
            )
        try:
            location_id = int(sample["locationId"])
        except (KeyError, TypeError, ValueError) as e:
            raise ElevationLookupError(
                "Error when querying USGS 3DEP service: sample is missing a usable locationId"
            ) from e
        if not 0 <= location_id < n_points:
            raise ElevationLookupError(
                f"Error when querying USGS 3DEP service: locationId {location_id} is "
                f"outside the {n_points} points requested"
            )
        return location_id

    @staticmethod
    def _parse_value(sample: Dict[str, Any]) -> Optional[float]:
        """Elevation in meters, or ``None`` where the service reports no value.

        ``value`` arrives as a JSON string, and no-data cells come back as
        ``NaN``/``None``/an empty string depending on the underlying raster.
        """
        raw = sample.get("value")
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError) as e:
            raise ElevationLookupError(
                f"Error when querying USGS 3DEP service: elevation is not a number: {raw!r}"
            ) from e
        if not np.isfinite(value):
            return None
        return value
