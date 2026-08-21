# Installation

GradeIT requires **Python 3.10 or newer**.

```bash
pip install gradeit
```

To install from source:

```bash
git clone https://github.com/NatLabRockies/gradeit.git
cd gradeit
pip install .
```

## Extras

The core install includes NumPy, `requests` for the default online elevation model, and a
GeoTIFF reader. Optional features use extras:

```bash
pip install gradeit[pandas]  # DataFrame input and GradeResult.to_dataframe()
pip install gradeit[plot]    # interactive folium map colored by grade
pip install gradeit[pandas,plot]
```

GradeIT does not require pandas. `gradeit()` accepts NumPy arrays, dictionaries, and lists of
`(latitude, longitude)` pairs. It returns NumPy arrays. Install pandas only for DataFrame input or
output.

## No GDAL required

GradeIT reads USGS GeoTIFFs with [tifffile](https://pypi.org/project/tifffile/) and
[imagecodecs](https://pypi.org/project/imagecodecs/). It does not use GDAL or rasterio. PyPI wheels
install on Linux, macOS, and Windows. You should not need a system geospatial stack.

The tradeoff is that GradeIT only reads the raster type from the USGS 3DEP program: single-band, north-up, geographic longitude/latitude GeoTIFFs.

## Verifying the install

```python
import gradeit
```

Test a couple of points.

```python
from gradeit import gradeit

# Two points a few hundred feet apart on a Colorado highway.
result = gradeit([(39.7392, -105.0), (39.7398, -105.0)])
print(result.elevation_ft_unfiltered)
```

## Development setup

The project uses [pixi](https://pixi.sh) for environments and tasks. After you
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
pixi run -e dev check   # ruff format + lint, dprint, mypy, and the test suite
pixi run -e dev test    # just the tests
```

See [Contributing](developers/contributing) for the full workflow, and
[Building the Docs](developers/build_the_docs) for this site.
