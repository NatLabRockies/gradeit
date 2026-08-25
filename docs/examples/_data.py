"""Shared data loading for the documentation examples.

The examples run on small DEM crops and trace slices committed under
``docs/data/`` so the docs build offline in seconds. See
``scripts/make_docs_data.py`` for how they were produced, and
``docs/elevation_data.md`` for how to point gradeit at the real full-size tiles.

The leading underscore keeps this out of the ``*example.py`` glob that the
notebook converter uses.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Resolve relative to this file so the examples work from any working directory
# (CI runs them from the repo root; jupyter-book executes them from docs/).
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TILE_DIR = DATA_DIR / "tiles"


def load_trace(name: str) -> tuple[list[float], list[float]]:
    """Return ``(latitudes, longitudes)`` for a committed demo trace."""
    path = DATA_DIR / "traces" / f"{name}.csv"
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return (
        [float(r["latitude"]) for r in rows],
        [float(r["longitude"]) for r in rows],
    )


def load_coords(name: str) -> list[tuple[float, float]]:
    """Return a demo trace as a list of ``(latitude, longitude)`` pairs.

    That is one of the input forms ``gradeit()`` accepts directly, so the
    examples can stay pandas-free where pandas is not the point.
    """
    lats, lons = load_trace(name)
    return list(zip(lats, lons))
