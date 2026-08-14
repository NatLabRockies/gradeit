# Installation

GradeIT requires **Python 3.10 or newer**.

```bash
pip install gradeit
```

Or from source:

```bash
git clone https://github.com/NREL/gradeit.git
cd gradeit
pip install .
```

## Extras

The core install is deliberately small — numpy plus a pure-Python GeoTIFF reader. Optional
features live behind extras:

```bash
pip install gradeit[pandas]  # DataFrame input and GradeResult.to_dataframe()
pip install gradeit[plot]    # interactive folium map colored by grade
pip install gradeit[pandas,plot]
```

GradeIT has no hard dependency on pandas. `gradeit()` accepts numpy arrays, dicts, and plain
lists of `(latitude, longitude)` pairs, and returns numpy arrays — so pandas is only needed if
you want to hand it a DataFrame or get one back.

## No GDAL required

GradeIT reads USGS GeoTIFFs through [tifffile](https://pypi.org/project/tifffile/) and
[imagecodecs](https://pypi.org/project/imagecodecs/) rather than GDAL or rasterio. Everything
installs from PyPI wheels on Linux, macOS, and Windows, with no system geospatial stack and no
conda environment needed. CI verifies this on all three platforms.

The trade-off is that GradeIT reads the specific kind of raster the USGS 3DEP program ships:
single-band, north-up, geographic (lon/lat) GeoTIFFs. Projected or rotated rasters are rejected
with a clear error rather than silently sampled at the wrong place.

## Verifying the install

```python
import gradeit

print(gradeit.__all__)
```

To check a real lookup end to end without downloading any raster tiles, use the online query
service — it needs no setup, but issues one HTTP request per point, so keep it to a handful:

```python
from gradeit import gradeit

# Two points a few hundred feet apart on a Colorado highway.
result = gradeit([(39.7392, -105.0), (39.7398, -105.0)])
print(result.elevation_ft)
```

For anything larger than a spot check, see [Elevation Data](elevation_data).

## Development setup

The project uses [pixi](https://pixi.sh) to manage environments and tasks. After
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
pixi run -e dev check   # ruff format + lint, dprint, mypy, and the test suite
pixi run -e dev test    # just the tests
```

See [Contributing](developers/contributing) for the full workflow, and
[Building the Docs](developers/build_the_docs) for this site.
