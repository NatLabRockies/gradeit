# GradeIT

Road Grade Inference Tool (GradeIT) - a python package, developed by the National Laboratory of
the Rockies, to append elevation and road grade to a sequence of GPS points.

**📖 [Full documentation](https://nrel.github.io/gradeit/)**

## Overview

GradeIT looks up and filters elevation and derives road grade from the
[USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep) to append to GPS
points, typically for vehicles traveling on paved roads. The python package offers options to use
either the freely accessible USGS [Elevation Point Query Service](https://epqs.nationalmap.gov/v1/)
or a locally available raster database of the elevation model, which provides much faster results.

The USGS model is **bare-earth**: it describes the ground, not the road. Where a road crosses water
or a valley on a structure, the raw lookup returns what is underneath, and differentiating that
produces grade spikes of tens of percent that no vehicle ever drove. Removing those without
flattening the real terrain around them is most of what GradeIT does.

## Setup

gradeit requires python 3.10 or newer.

```bash
pip install gradeit
```

or install from source:

```bash
git clone https://github.com/NREL/gradeit.git
cd gradeit
pip install .
```

gradeit has no hard dependency on pandas. Install the optional extras you need:

```bash
pip install gradeit[pandas]  # DataFrame input + GradeResult.to_dataframe()
pip install gradeit[plot]    # interactive folium map of the trace colored by grade
```

Everything installs from PyPI wheels on Linux, macOS, and Windows - no GDAL, no system geospatial
stack. See [Installation](https://nrel.github.io/gradeit/installation.html).

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

Use the `_filtered` arrays. `gradeit()` returns a `GradeResult` of numpy arrays and never mutates
its input.

Elevation comes from an `ElevationModel`, selected with the `elevation_model` argument. By default
it uses `USGSApi()` - the online query service, which needs no setup but issues one request per
point. For whole-trace lookups, point `USGSLocal` at a local copy of the raster tiles instead:

```python
from gradeit import USGSLocal, gradeit

result = gradeit(data, elevation_model=USGSLocal("path/to/tiles/"))
```

By default `gradeit()` also runs a `Wood2014Filter` over the elevation profile, implementing the
five-step filtration routine of Wood et al. (2014). Pass `elevation_filter=None` to disable
filtering, or a sequence of filters to compose them.

## Documentation

The [documentation site](https://nrel.github.io/gradeit/) has runnable examples and the full
reference:

- [Quickstart](https://nrel.github.io/gradeit/quickstart.html) - input forms, output fields, and
  the two choices that matter
- [Elevation Data](https://nrel.github.io/gradeit/elevation_data.html) - getting the USGS tiles,
  and how much disk they need
- [Methodology](https://nrel.github.io/gradeit/methodology.html) - the Wood et al. (2014) routine,
  step by step
- [Filters](https://nrel.github.io/gradeit/filters.html) - every parameter, with defaults and
  tuning guidance
- [API Reference](https://nrel.github.io/gradeit/api_docs.html)

The example pages run on small committed data crops, so they execute in seconds:

- [Your First Grade Profile](https://nrel.github.io/gradeit/examples/01_basic_example.html)
- [How Filtration Works](https://nrel.github.io/gradeit/examples/02_filtering_example.html)
- [Bare-Earth Bridges](https://nrel.github.io/gradeit/examples/03_bridges_example.html)
- [Mapping a Trace](https://nrel.github.io/gradeit/examples/04_plotting_example.html)
- [Custom Elevation Sources](https://nrel.github.io/gradeit/examples/05_custom_elevation_model_example.html)

## Examples on real data

`examples/` holds the full-scale walkthroughs. Unlike the documentation examples, these run over
complete traces and need the real USGS tiles downloaded first (hundreds of MB to ~14 GB), so they
are meant to be run by hand rather than on CI:

- `examples/basic.py` - a 45-mile Colorado trip end to end, including the interactive map. Needs
  the Colorado tiles.
- `examples/bridge_filter_long_spans.py` - 65 miles up the east side of San Francisco Bay, crossing
  two artifacts on opposite sides of the default filter's competence. Needs `n38w123` and `n39w123`
  (~705 MB).

Download tiles with `scripts/get_usgs_tiles.py`; see `scripts/README.md`.

## Development

This project uses [pixi](https://pixi.sh) to manage development environments and tasks. After
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
pixi run -e dev check   # ruff format + lint, dprint (markdown), mypy, and tests
pixi run -e dev test    # run the test suite
```

Formatting and linting use [ruff](https://docs.astral.sh/ruff/), and markdown files are formatted
with [dprint](https://dprint.dev/). To build the documentation site:

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

`CITATION.cff` in the repository root carries the same metadata in machine-readable form; GitHub
renders it as "Cite this repository" in the sidebar.

The filtration methodology GradeIT implements is described separately in Wood et al. (2014) - cite
that as well if the method itself is what matters to your work. See
[Methodology](https://nrel.github.io/gradeit/methodology.html).
