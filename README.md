# GradeIT

Road Grade Inference Tool (GradeIT) - a python package, developed by the National Laboratory of the Rockies,
to append elevation and road grade to a sequence of GPS points.

## Overview

GradeIT looks up and filters elevation and derives road grade from the
[USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep) to append to GPS points, typically
for vehicles traveling on paved roads. The python package offers options to use either the the freely accessible USGS
[Elevation Point Query Service](https://nationalmap.gov/epqs/) or a locally available raster database of the elevation
model, which provides much faster results.

## Setup

gradeit requires python 3.10 or newer. To use the library, install it from source:

```bash
git clone https://github.com/NatLabRockiesgradeit.git
pip install .
```

or install the published package directly:

```bash
pip install gradeit
```

gradeit has no hard dependency on pandas. Install the optional extras you need:

```bash
pip install gradeit[pandas]   # DataFrame input + GradeResult.to_dataframe()
pip install gradeit[api]       # the online USGS Elevation Point Query Service source
```

## Development

This project uses [pixi](https://pixi.sh) to manage development environments and tasks.
After [installing pixi](https://pixi.sh/latest/#installation), set up the dev environment:

```bash
pixi install -e dev
```

Common tasks are defined in `pyproject.toml` under `[tool.pixi.feature.dev.tasks]`:

```bash
pixi run -e dev check   # ruff format + lint, dprint (markdown), mypy, and tests
pixi run -e dev test    # run the test suite
```

Formatting and linting use [ruff](https://docs.astral.sh/ruff/), and markdown files are
formatted with [dprint](https://dprint.dev/).

## Getting Started

```python
from gradeit import gradeit

# `data` can be a pandas DataFrame, a numpy (n, 2) array, a dict of
# {"latitude": [...], "longitude": [...]}, or an iterable of (lat, lon) pairs.
result = gradeit(data, source="usgs-api")

result.elevation_ft   # numpy array of elevation (feet)
result.grade_dec       # numpy array of decimal road grade (rise/run)
result.to_dataframe()  # tabular view (requires gradeit[pandas])
```

`gradeit()` returns a `GradeResult` of numpy arrays and never mutates its input.
For the full, runnable walkthrough see `examples/basic.py`.

## USGS Elevation Data

The United States Geological Survey offers a variety of products as a part of the [National Map](https://www.usgs.gov/core-science-systems/national-geospatial-program/national-map) project, including bare-earth elevation datasets. The 1/3 arc-second elevation dataset is continuous for the coterminous United States and is therefore used in GradeIT. Appending elevation and grade to 1000+ points benefits significantly from having a local or network copy of the required USGS elevation data.

NLR has the 1/3 arc-second raster data downloaded to on-site compute resources for large scale needs. Individual users can access the same raster data [here](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/13/TIFF/current/).

### Download Script

This repository comes with a script you can use to download USGS tiles yourself. You can use the script like this:

```bash
python scripts/get_usgs_tiles.py --output-dir path/to/output/
```

The script will then proceed to download all tiles into `path/to/output/` which can be used when running gradeit:

```python
result = gradeit(
    df,
    source="usgs-local",
    usgs_db_path="path/to/output/",
    sampling="bilinear",  # "bilinear" (default) or "nearest"
)
```

Elevation is sampled from the DEM with bilinear interpolation by default, which is smoother and
more accurate than the legacy nearest-neighbor lookup (still available via `sampling="nearest"`).
Points outside the available tiles, or over DEM no-data cells, are returned as `NaN`.

You can also use the script to just download a subset of tiles.

This example would use the `scripts/colorado_tiles.txt` file to just download raster tiles that cover the state of colorado:

```console
python get_usgs_tiles.py --output-dir colorado_tiles/ --tile-data colorado_tiles.txt --nprocs 8
```

## Filters

Given the spatial noise that can be present in GPS data and the 1/3 arc-second resolution of the digital elevation
model being employed, outliers and unrealistic topographical features can be present in the raw elevation profiles.
gradeit makes two kinds of filtering available, and the distinction matters:

- **Elevation filters** (`ElevationFilter`) smooth the **elevation** profile _before_ grade is computed. The built-in
  `SavitzkyGolayFilter` removes DEM/GPS noise that would otherwise produce spurious grade spikes.
- **Grade filters** (`GradeFilter`) correct the **grade** profile _after_ it is computed. The built-in
  `BridgeGradeFilter` handles bridges and overpasses (see below).

Both are passed to `gradeit()` as instances (or `True` for the default), so you can configure or swap them:

```python
from gradeit import gradeit, SavitzkyGolayFilter, BridgeGradeFilter

result = gradeit(
    data,
    source="usgs-local",
    usgs_db_path="path/to/output/",
    elevation_filter=SavitzkyGolayFilter(window=21),  # or True for the default
    grade_filter=BridgeGradeFilter(),                  # or True for the default
)
```

When filtering runs, the smoothed/corrected profiles are available as `result.elevation_ft_filtered` and
`result.grade_dec_filtered`; the raw `result.elevation_ft` / `result.grade_dec` are always preserved.

The primary elevation-filtering procedure is summarized in the figure below from Wood et al in 2014.

<img src="docs/imgs/grade_filters.png">

<sub>Wood, Eric, E. Burton, A. Duran, and J. Gonder. Appending High-Resolution Elevation Data to GPS Speed Traces for
Vehicle Energy Modeling and Simulation. No. NatLabRockiesTP-5400-61109. National Renewable Energy Lab.(NLR), Golden, CO
(United States), 2014.<sub>

Additionally, since the USGS Digital Elevation Model is a "bare earth" model, road infrastructure features (i.e.
bridges and overpasses) are often not represented in the data. Rather, the "bare earth" model represents the valley or
body of water that is being spanned. The `BridgeGradeFilter` grade filter explicitly handles this by detecting the
flat bare-earth span inside a dip and zeroing the grade across it, effectively "building" a bridge to span the river,
valley, etc. where necessary.
