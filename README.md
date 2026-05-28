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
pip install gradeit[plot]      # interactive folium map of the trace colored by grade
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
result = gradeit(data)

result.elevation_ft   # numpy array of elevation (feet)
result.grade_dec       # numpy array of decimal road grade (rise/run)
result.to_dataframe()  # tabular view (requires gradeit[pandas])
```

`gradeit()` returns a `GradeResult` of numpy arrays and never mutates its input.
Elevation comes from an `ElevationModel`, selected with the `elevation_model`
argument. By default it uses `USGSApi()` — the online USGS Elevation Point Query
Service, which needs no setup. For whole-trace lookups, point `USGSLocal` at a
local copy of the raster tiles instead (see below); it is much faster. By default
`gradeit()` also runs a `BridgeFilter` over the elevation profile (see _Filters_);
pass `elevation_filter=None` to disable filtering.
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
from gradeit import gradeit, USGSLocal

result = gradeit(
    df,
    elevation_model=USGSLocal(
        "path/to/output/",
        sampling="bilinear",  # "bilinear" (default) or "nearest"
    ),
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
gradeit cleans up the elevation profile through one or more `ElevationFilter`s applied before grade is computed:

- `BridgeFilter` interpolates elevation across bridge and overpass artifacts the bare-earth DEM does not represent
  (see below). This is the **default** filter — `gradeit()` applies it unless you pass a different
  `elevation_filter` (or `None` to disable filtering).
- `SavitzkyGolayFilter` removes DEM/GPS noise that would otherwise produce spurious grade spikes.

Pass a single filter or a sequence; sequences are applied in order, each consuming the previous filter's output:

```python
from gradeit import gradeit, USGSLocal, SavitzkyGolayFilter, BridgeFilter

result = gradeit(
    data,
    elevation_model=USGSLocal("path/to/output/"),
    elevation_filter=[BridgeFilter(), SavitzkyGolayFilter(window=21)],
)
```

The recommended order is `BridgeFilter` first, then `SavitzkyGolayFilter`: bridge correction produces a clean
profile for Savitzky-Golay to smooth, whereas smoothing first attenuates the dip magnitude `BridgeFilter` keys on.

When filtering runs, the cleaned profile is available as `result.elevation_ft_filtered` and grade recomputed from it
as `result.grade_dec_filtered`; the raw `result.elevation_ft` / `result.grade_dec` are always preserved.

## Plotting

Install the `plot` extra (`pip install gradeit[plot]`) for `plot_grade_map`, an
interactive folium map of the trace with each segment colored by its grade.
This is handy for spot-checking DEM artifacts -- bridges and overpasses show
up as sharp negative grade spikes on the raw layer where the bare-earth DEM
dips into the valley underneath.

```python
from gradeit import gradeit, USGSLocal, BridgeFilter, SavitzkyGolayFilter

result = gradeit(
    data,
    elevation_model=USGSLocal("path/to/output/"),
    elevation_filter=[BridgeFilter(), SavitzkyGolayFilter()],
)

# Returns a folium.Map; in Jupyter it renders inline, or save to HTML:
m = result.plot_map()           # equivalent to plot_grade_map(result)
m.save("trace.html")
```

When the result has both raw and filtered grade, `plot_map()` shows them as
toggleable layers so you can flip back and forth and see exactly where the
filter intervened. Hovering a segment reveals its grade, elevation, and
length. Pass `grade="raw"`, `"filtered"`, or `"both"` to override, and
`grade_range_pct=(-8, 8)` to fix the color scale.

> **VS Code Interactive Window / untrusted notebooks**: inline display can show
> "Make this notebook trusted to load map". The VS Code Interactive Window has
> no trust toggle; `.ipynb` files do via Command Palette → "Notebook: Manage
> Trust". The simplest workaround is to render via an `IFrame` from a saved
> file (see `examples/basic.py`) or just open the saved HTML in a browser.

The primary elevation-filtering procedure is summarized in the figure below from Wood et al in 2014.

<img src="docs/imgs/grade_filters.png">

<sub>Wood, Eric, E. Burton, A. Duran, and J. Gonder. Appending High-Resolution Elevation Data to GPS Speed Traces for
Vehicle Energy Modeling and Simulation. No. NatLabRockiesTP-5400-61109. National Renewable Energy Lab.(NLR), Golden, CO
(United States), 2014.<sub>

Additionally, since the USGS Digital Elevation Model is a "bare earth" model, road infrastructure features (i.e.
bridges and overpasses) are often not represented in the data. Rather, the "bare earth" model represents the valley or
body of water that is being spanned. The `BridgeFilter` elevation filter handles this by detecting dips in elevation
that sit below the surrounding road surface on both sides and linearly interpolating the road's elevation across the
span, effectively "building" a bridge to span the river, valley, etc. where necessary. Grade is then recomputed from
the corrected elevation so elevation and grade stay internally consistent.
