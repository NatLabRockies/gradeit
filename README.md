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

result.elevation_ft_filtered  # numpy array of filtered elevation (feet)
result.grade_dec_filtered     # numpy array of decimal road grade (rise/run)
result.elevation_ft           # the raw DEM lookup, always preserved
result.grade_dec              # grade from the raw lookup, unfiltered
result.to_dataframe()         # tabular view (requires gradeit[pandas])
```

Use the `_filtered` arrays. The raw DEM profile contains bridge/overpass
artifacts and sampling noise that produce grade spikes of tens of percent —
Wood et al. specifically note these are "unsuitable for downstream vehicle
simulation programs."

`gradeit()` returns a `GradeResult` of numpy arrays and never mutates its input.
Elevation comes from an `ElevationModel`, selected with the `elevation_model`
argument. By default it uses `USGSApi()` — the online USGS Elevation Point Query
Service, which needs no setup. For whole-trace lookups, point `USGSLocal` at a
local copy of the raster tiles instead (see below); it is much faster. By default
`gradeit()` also runs a `Wood2014Filter` over the elevation profile (see
_Filters_); pass `elevation_filter=None` to disable filtering.
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

Elevation is sampled from the DEM with bilinear interpolation by default, which is smoother than
the nearest-neighbor lookup (still available via `sampling="nearest"`). Both samplers are
registered on pixel centers, so bilinear at a pixel's own center returns that pixel's value
exactly. Points outside the available tiles, or over DEM no-data cells, are returned as `NaN`.

You can also use the script to just download a subset of tiles.

This example would use the `scripts/colorado_tiles.txt` file to just download raster tiles that cover the state of colorado:

```console
python get_usgs_tiles.py --output-dir colorado_tiles/ --tile-data colorado_tiles.txt --nprocs 8
```

## Filters

Given the spatial noise that can be present in GPS data and the 1/3 arc-second resolution of the digital elevation
model being employed, outliers and unrealistic topographical features can be present in the raw elevation profiles.
gradeit cleans up the elevation profile through one or more `ElevationFilter`s applied before grade is computed:

- **`Wood2014Filter`** implements the five-step filtration routine of Wood et al. (2014) — see
  _Methodology_ below. This is the **default**: `gradeit()` applies it unless you pass a different
  `elevation_filter` (or `None` to disable filtering).
- `BridgeFilter` is a targeted correction for bare-earth bridge and overpass artifacts: it detects
  dips that sit below the surrounding road on both sides and interpolates across them. It handles
  spans much longer than `Wood2014Filter`'s outlier rejection will accept, but it needs tuning —
  **set `baseline_radius_ft` to the scale of the spans you are correcting.** Its one-mile default
  suits gentle terrain; on a trace that crosses real valleys, a descent and climb inside that
  radius reads as one huge "dip" and gets flattened. See `examples/bridge_artifact.py`.
- `SavitzkyGolayFilter` smooths in the index (point) domain. Superseded by `Wood2014Filter` for
  most uses — because GPS traces are sampled in time, a fixed point-count window has a physical
  width that varies with vehicle speed.

Pass a single filter or a sequence; sequences are applied in order, each consuming the previous filter's output:

```python
from gradeit import gradeit, USGSLocal, BridgeFilter, Wood2014Filter

result = gradeit(
    data,
    elevation_model=USGSLocal("path/to/output/"),
    elevation_filter=[BridgeFilter(), Wood2014Filter()],
)
```

`BridgeFilter` goes first if you use it: it keys on raw dip magnitude, which any smoother attenuates.

When filtering runs, the cleaned profile is available as `result.elevation_ft_filtered` and grade recomputed from it
as `result.grade_dec_filtered`; the raw `result.elevation_ft` / `result.grade_dec` are always preserved.

### Tuning

`Wood2014Filter` is a frozen dataclass; every knob is a constructor argument. The paper specifies
no numeric values, so these defaults are this package's choices — see the class docstring for the
reasoning behind each.

```python
Wood2014Filter(
    interval_ft=100.0,            # uniform distance grid (step B)
    savgol_window_ft=600.0,       # Savitzky-Golay width, in feet not points
    savgol_polyorder=3,
    binomial_sigma_ft=100.0,      # binomial width, as a Gaussian-equivalent sigma
    residual_threshold_ft=8.0,    # step D discard threshold on |pre - post|
)
```

Widen `savgol_window_ft` for a smoother, lower-noise grade signal at the cost of attenuating
short real features; lower `residual_threshold_ft` to reject more aggressively.

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

The basemap defaults to `CartoDB positron` — muted grey, so the grade colors carry the signal.
Override it with `tiles=`, e.g. `"CartoDB Voyager"` (more road labeling), `"CartoDB dark_matter"`,
or `"OpenStreetMap"`.

> **Blank map / 403 errors on the basemap**: openstreetmap.org's
> [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) blocks heavy or
> automated clients, and a blocked client gets 403s instead of tiles. That is why `OpenStreetMap`
> is not the default here. If you switch to it and the map comes up blank, that is the cause —
> switch back to one of the CartoDB basemaps.

> **VS Code Interactive Window / untrusted notebooks**: inline display can show
> "Make this notebook trusted to load map". The VS Code Interactive Window has
> no trust toggle; `.ipynb` files do via Command Palette → "Notebook: Manage
> Trust". The simplest workaround is to render via an `IFrame` from a saved
> file (see `examples/basic.py`) or just open the saved HTML in a browser.

## Methodology

The default filtration routine implements the five steps summarized in the figure below, from
Wood et al. (2014).

<img src="docs/imgs/grade_filters.png">

<sub>Wood, Eric, E. Burton, A. Duran, and J. Gonder. Appending High-Resolution Elevation Data to GPS Speed Traces for
Vehicle Energy Modeling and Simulation. No. NatLabRockiesTP-5400-61109. National Renewable Energy Lab.(NLR), Golden, CO
(United States), 2014.<sub>

`Wood2014Filter` carries out steps B through E:

| Step  | What happens                                                                                                                          |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **B** | Elevation is downsampled onto a uniformly spaced distance grid, each node the **median** of the raw points falling in it.             |
| **C** | The downsampled profile is passed through a combined **Savitzky-Golay and binomial** filter, and the pre/post difference is computed. |
| **D** | Nodes whose filtration residual exceeds a threshold are **discarded and backfilled** by interpolation.                                |
| **E** | The backfilled profile is filtered again, then elevation at the **original distance values** is recovered by interpolation.           |

Grade is always recomputed from the final filtered elevation, matching the paper's definition of
grade as the derivative of elevation with respect to distance.

Step B is the load-bearing one. GPS traces are sampled in _time_, so their spacing in _distance_
varies with speed — on the 45-mile sample trace in `examples/data/`, median point spacing is
115 ft while the 5th and 95th percentiles are 10 ft and 424 ft. Smoothing such a signal by point
index gives a filter whose physical cutoff swings more than sixfold along a single trace.
Resampling onto a fixed distance grid first makes that cutoff a fixed number of feet everywhere,
which is why the paper specifies steps C–E on the uniform grid.

**The paper specifies no numeric parameter values** — not the grid interval, the filter widths, or
the discard threshold. The defaults in `Wood2014Filter` are this package's choices, reasoned from
the DEM's ~33 ft post spacing and 2.44 m vertical RMSE and documented in the class docstring. They
are a starting point, not a reproduction of the paper's own settings, which are not published.

`scripts/reproduce_figure4.py` reproduces the paper's Figure 4 — raw versus filtered elevation and
grade — from a real trace, for visual comparison.

### Bridges and overpasses

Since the USGS Digital Elevation Model is a "bare earth" model, road infrastructure features (i.e.
bridges and overpasses) are often not represented in the data. Rather, the "bare earth" model represents the valley or
body of water that is being spanned. Step D of the routine above catches these along with every other
anomaly, since a bridge artifact is exactly a large filtration residual.

The separate `BridgeFilter` targets them directly, by detecting dips in elevation
that sit below the surrounding road surface on both sides and linearly interpolating the road's elevation across the
span, effectively "building" a bridge to span the river, valley, etc. where necessary. It is worth adding
ahead of `Wood2014Filter` for spans longer than the routine's `max_discard_len_ft` will accept.

Tune `baseline_radius_ft` when you do. A real valley is also a dip below the road on both sides, so
geometry alone cannot tell the two apart — the baseline radius is what draws the line, and its
one-mile default is only right for gentle terrain.

Two examples cover this end to end:

- `examples/bridge_artifact.py` isolates a single creek crossing from `sample_trip_1`, confirms it
  is a bare-earth notch rather than a GPS error, and shows the default `Wood2014Filter` fixing it
  while stock `BridgeFilter` silently flattens a mile of genuine 172 ft valley around it. Needs
  local USGS tiles.
- `examples/bridge_filter_long_spans.py` uses `SF_bridge_trip_segment.csv`, which crosses two real
  artifacts on opposite sides of the default's competence: an ~800 ft crossing the default removes
  by itself, and the 5,332 ft Carquinez Strait crossing on I-80, where the bare-earth DEM returns
  the water surface 166 ft below the deck and the raw grade hits +89%. The default cannot touch the
  long one at any `savgol_window_ft`; `BridgeFilter` clears it once `baseline_radius_ft` covers the
  span. Needs the `n38w123` and `n39w123` tiles (~705 MB).
