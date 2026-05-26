# GradeIT

Road Grade Inference Tool (GradeIT) - a python package, developed by the National Renewable Energy Laboratory,
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
git clone https://github.com/NREL/gradeit.git
pip install .
```

or install the published package directly:

```bash
pip install gradeit
```

## Development

This project uses [pixi](https://pixi.sh) to manage development environments and tasks.
After [installing pixi](https://pixi.sh/latest/#installation), set up the dev environment:

```bash
pixi install -e dev
```

The native geospatial stack (GDAL via rasterio, shapely, etc.) is pulled from conda-forge so
it is self-contained and reproducible.

Common tasks are defined in `pyproject.toml` under `[tool.pixi.feature.dev.tasks]`:

```bash
pixi run -e dev check   # ruff format + lint, dprint (markdown), mypy, and tests
pixi run -e dev test    # run the test suite
```

Formatting and linting use [ruff](https://docs.astral.sh/ruff/), and markdown files are
formatted with [dprint](https://dprint.dev/).

## Getting Started

In this repository, `examples/basic.py` will demonstrate basic application of the gradeit package.

## USGS Elevation Data

The United States Geological Survey offers a variety of products as a part of the [National Map](https://www.usgs.gov/core-science-systems/national-geospatial-program/national-map) project, including bare-earth elevation datasets. The 1/3 arc-second elevation dataset is continuous for the coterminous United States and is therefore used in GradeIT. Appending elevation and grade to 1000+ points benefits significantly from having a local or network copy of the required USGS elevation data.

NREL has the 1/3 arc-second raster data downloaded to on-site compute resources for large scale needs. Individual users can access the same raster data [here](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/13/TIFF/current/).

### Download Script

This repository comes with a script you can use to download USGS tiles yourself. You can use the script like this:

```bash
python scripts/get_usgs_tiles.py --output-dir path/to/output/
```

The script will then proceed to download all tiles into `path/to/output/` which can be used when running gradeit:

```python
results = gradeit(
    df=df,
    source="usgs-local",
    usgs_db_path="path/to/output/",
)
```

You can also use the script to just download a subset of tiles.

This example would use the `scripts/colorado_tiles.txt` file to just download raster tiles that cover the state of colorado:

```console
python get_usgs_tiles.py --output-dir colorado_tiles/ --tile-data colorado_tiles.txt --nprocs 8
```

## Filters

Given the spatial noise that can be present in GPS data and the 1/3 arc-second resolution of the digital elevation
model being employed, outliers and unrealistic topographical features can be present in the raw elevation profiles.
Therefore, a series of filtering procedures can be applied to the elevation data, if desired by the user. The primary
filter procedure is summarized in the figure below from Wood et al in 2014.

<img src="docs/imgs/grade_filters.png">

<sub>Wood, Eric, E. Burton, A. Duran, and J. Gonder. Appending High-Resolution Elevation Data to GPS Speed Traces for
Vehicle Energy Modeling and Simulation. No. NREL/TP-5400-61109. National Renewable Energy Lab.(NREL), Golden, CO
(United States), 2014.<sub>

Additionally, since the USGS Digital Elevation Model is a "bare earth" model, road infrastructure features (i.e.
bridges and overpasses) are often not represented in the data. Rather, the "bare earth" model represents the valley or
body of water that is being spanned. GradeIT has optional filtering routines to explicitly handle this by
"building" a bridge to span the river, valley, etc where necessary.
