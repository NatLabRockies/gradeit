# GradeIT

GradeIT is a Python package from the National Laboratory of the Rockies. It adds elevation and road
grade to a sequence of GPS points.

**📖 [Full documentation](https://nrel.github.io/gradeit/)**

## Overview

GradeIT gets elevation from the [USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep). It filters the elevation and calculates
road grade. GradeIT is for GPS points from vehicles on paved roads.

You can use the online USGS [3DEP](https://www.usgs.gov/3d-elevation-program) service or local
raster tiles. The online service is easy to use and batches its requests. Local tiles are faster
still.

The USGS model is **bare-earth**. It shows the ground, not the road. A bridge over water or a valley
returns the elevation below the bridge. This data creates large grade spikes. GradeIT removes these
spikes and preserves nearby terrain.

## Setup

GradeIT requires Python 3.10 or newer.

```bash
pip install gradeit
```

To install from source:

```bash
git clone https://github.com/NREL/gradeit.git
cd gradeit
pip install .
```

GradeIT does not require pandas. Install these optional extras as needed:

```bash
pip install gradeit[pandas]  # DataFrame input + GradeResult.to_dataframe()
pip install gradeit[plot]    # interactive folium map of the trace colored by grade
```

PyPI wheels install on Linux, macOS, and Windows. You do not need GDAL or a system geospatial stack.
See [Installation](https://nrel.github.io/gradeit/installation.html).

## Getting Started

```python
from gradeit import gradeit

# `data` can be a pandas DataFrame, a numpy (n, 2) array, a dict of
# {"latitude": [...], "longitude": [...]}, or an iterable of (lat, lon) pairs.
result = gradeit(data)

result.elevation_ft_filtered  # numpy array of filtered elevation (feet)
result.grade_dec_filtered  # numpy array of decimal road grade (rise/run)
result.elevation_ft_unfiltered  # the raw DEM lookup, always preserved
result.grade_dec_unfiltered  # grade from the raw lookup
result.to_dataframe()  # tabular view (requires gradeit[pandas])
```

Use the `_filtered` arrays. `gradeit()` returns a `GradeResult` that contains NumPy arrays. It does
not change its input.

The `elevation_model` argument selects an `ElevationModel`. By default, GradeIT uses `USGSApi()`.
This online service needs no setup and batches up to 1,000 points per request. Use `USGSLocal` with
local raster tiles to avoid depending on a public service:

```python
from gradeit import USGSLocal, gradeit

result = gradeit(data, elevation_model=USGSLocal("path/to/tiles/"))
```

By default, `gradeit()` uses `Wood2014Filter` on the elevation profile. This filter uses the
five-step method from Wood et al. (2014). Set `elevation_filter=None` to disable filtering. You can
also pass a sequence of filters.

## Documentation

The [documentation site](https://nrel.github.io/gradeit/) has runnable examples and the full API
reference:

- [Quickstart](https://nrel.github.io/gradeit/quickstart.html) - input, output, elevation models,
  and filters
- [Elevation Data](https://nrel.github.io/gradeit/elevation_data.html) - USGS tiles and disk space
- [Methodology](https://nrel.github.io/gradeit/methodology.html) - the Wood et al. (2014) method
- [Filters](https://nrel.github.io/gradeit/filters.html) - parameters, defaults, and tuning
- [API Reference](https://nrel.github.io/gradeit/api_docs.html)

The example pages use small data crops in the repository. They run in seconds:

- [Your First Grade Profile](https://nrel.github.io/gradeit/examples/01_basic_example.html)
- [How Filtration Works](https://nrel.github.io/gradeit/examples/02_filtering_example.html)
- [Bare-Earth Bridges](https://nrel.github.io/gradeit/examples/03_bridges_example.html)
- [Mapping a Trace](https://nrel.github.io/gradeit/examples/04_plotting_example.html)
- [Custom Elevation Sources](https://nrel.github.io/gradeit/examples/05_custom_elevation_model_example.html)

## Examples on real data

`examples/` contains full examples. Unlike the documentation examples, they use complete traces and
need real USGS tiles. The tiles need hundreds of MB to about 14 GB. Run these examples by hand, not
in CI:

- `examples/basic.py` - a 45-mile Colorado trip end to end, including the interactive map. Needs
  the Colorado tiles.
- `examples/bridge_filter_long_spans.py` - 65 miles on the east side of San Francisco Bay. It needs
  `n38w123` and `n39w123` (about 705 MB).

Download tiles with `scripts/get_usgs_tiles.py`; see `scripts/README.md`.

## Development

This project uses [pixi](https://pixi.sh) for development environments and tasks. After you
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
pixi run -e dev check   # ruff format + lint, dprint (markdown), mypy, and tests
pixi run -e dev test    # run the test suite
```

Formatting and linting use [ruff](https://docs.astral.sh/ruff/). Markdown files use
[dprint](https://dprint.dev/). To build the documentation site:

```bash
pixi install -e docs
pixi run -e docs docs_build
```

See [Contributing](https://nrel.github.io/gradeit/developers/contributing.html) and
[Building the Docs](https://nrel.github.io/gradeit/developers/build_the_docs.html).

## Citation

If you use GradeIT in published work, please cite the software:

> National Laboratory of the Rockies. _GradeIT: Road Grade Inference Tool_ (version 0.2.0)
> [Computer software]. https://github.com/NREL/gradeit

```bibtex
@software{gradeit,
  title    = {{GradeIT}: Road Grade Inference Tool},
  author   = {{National Laboratory of the Rockies}},
  version  = {0.2.0},
  url      = {https://github.com/NREL/gradeit},
  license  = {BSD-3-Clause}
}
```

`CITATION.cff` in the repository root has the same metadata in a machine-readable form. GitHub
shows it as "Cite this repository" in the sidebar.

Wood et al. (2014) describes the filter method. Cite that paper if the method is important to your
work. See
[Methodology](https://nrel.github.io/gradeit/methodology.html).
