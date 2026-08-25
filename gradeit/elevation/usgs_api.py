"""Online elevation lookup against the USGS 3DEP service.

Samples points in batches through the 3DEP ImageServer ``getSamples`` service.
"""

import json
import time
from collections.abc import Sequence
from typing import Any, ClassVar

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.elevation.elevation_model import ElevationModel
from gradeit.exceptions import ElevationLookupError, MissingDependencyError

URL = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples"

# The service returns at most 1,000 samples per request.
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
    Look up elevation from the public USGS 3DEP bare-earth service.

    Sends up to :data:`MAX_POINTS_PER_REQUEST` points in each request. Points
    outside service coverage return ``NaN``.

    Parameters
    ----------
    batch_size:
        Points per request. Values above :data:`MAX_POINTS_PER_REQUEST` are
        capped.
    sampling:
        ``"nearest"`` (default) returns the containing cell. ``"bilinear"``
        interpolates the surrounding cells.
    timeout:
        Per-request timeout in seconds.
    max_retries:
        Attempts for a timeout, connection error, or retryable HTTP status.

    More information is available at https://www.usgs.gov/3d-elevation-program
    """

    # ArcGIS values for the ``interpolation`` request parameter.
    _INTERPOLATION: ClassVar[dict[str, str]] = {
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

    def get_elevation(self, trace: list[Coordinate]) -> list[float]:
        if not trace:
            return []

        requests = _require_requests()
        elevation_ft = np.full(len(trace), np.nan, dtype=np.float64)

        # Reuse one connection for all batches.
        with requests.Session() as session:
            for start in range(0, len(trace), self.batch_size):
                chunk = trace[start : start + self.batch_size]
                samples = self._query_batch(session, chunk)
                for location_id, meters in samples.items():
                    elevation_ft[start + location_id] = meters * _FT_PER_M

        return elevation_ft.tolist()

    def _query_batch(self, session, chunk: Sequence[Coordinate]) -> dict[int, float]:
        """Sample one batch, returned as ``{index within chunk: meters}``.

        Points without data are absent from the mapping.
        """
        payload = self._build_payload(chunk)
        result = self._post_with_retry(session, payload, len(chunk))

        # The service can report an error in a successful HTTP response.
        if "error" in result:
            error = result["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            raise ElevationLookupError(f"Error when querying USGS 3DEP service: {message}")

        raw_samples = result.get("samples")
        if raw_samples is None:
            raise ElevationLookupError(
                "Error when querying USGS 3DEP service: no samples present in result"
            )

        samples: dict[int, float] = {}
        for sample in raw_samples:
            # ``locationId`` links each sample to its input point.
            location_id = self._parse_location_id(sample, len(chunk))
            value = self._parse_value(sample)
            if value is not None:
                samples[location_id] = value
        return samples

    def _build_payload(self, chunk: Sequence[Coordinate]) -> dict[str, str]:
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

    def _post_with_retry(self, session, payload: dict[str, str], n_points: int) -> dict[str, Any]:
        """POST one batch, retrying transient failures.

        Uses POST because a batch can exceed a practical URL length.
        """
        requests = _require_requests()
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            if attempt:
                # Wait longer after each failed request.
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
    def _parse_value(sample: dict[str, Any]) -> float | None:
        """Elevation in meters, or ``None`` where the service reports no value.

        The service sends values as JSON strings. Missing values may be
        ``NaN``, ``None``, or an empty string.
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
