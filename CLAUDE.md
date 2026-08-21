## Project overview

GradeIT (Road Grade Inference Tool) is a python package that appends elevation and road grade to a sequence of GPS points, sourcing elevation from the USGS Digital Elevation Model.

## Architecture

The public API is the top-level package: `from gradeit import gradeit, GradeResult, USGSApi, USGSLocal, Wood2014Filter, BridgeFilter, ...` (see `gradeit/__init__.py`). The orchestration lives in `gradeit/core.py`.

The methodology follows Wood et al. (2014), NLR/TP-5400-61109. When changing filtering or grade computation, check it against that paper — `README.md` has a _Methodology_ section mapping the paper's five steps onto the code.

- `gradeit()` accepts flexible input (DataFrame / numpy `(n,2)` / dict / iterable of `Coordinate` or `(lat, lon)`) via `gradeit/io.py:to_coordinates`, and returns a pandas-free `GradeResult` (numpy arrays + `.to_dataframe()` / `.to_dict()`). It never mutates its input. pandas is an optional dependency, imported lazily only in `GradeResult.to_dataframe()`.
- Every elevation/grade field on `GradeResult` carries an explicit `_unfiltered` or `_filtered` suffix (`elevation_ft_unfiltered`, `grade_dec_unfiltered`, `elevation_ft_filtered`, `grade_dec_filtered`), and `to_dict()` / `to_dataframe()` use those same names as column names. Nothing is bare: no field's provenance depends on remembering a default. Keep both halves in step when adding a field.
- Elevation comes from an `ElevationModel` (under `gradeit/elevation/`), passed via the `elevation_model` parameter. It defaults to `USGSApi()` (the online query service); `USGSLocal(path)` reads local raster tiles. There is no separate "source" concept — callers construct and pass the model directly. `requests` (used by `USGSApi`) is a core dependency but is imported lazily so `import gradeit` stays cheap.
- `USGSApi` batches points through the 3DEP ImageServer's `getSamples` operation. Three properties of that endpoint are load-bearing and easy to regress: it **silently truncates** above 1,000 points per request (returning HTTP 200 with `locationId` 0–999, and _not_ at the advertised `maxRecordCount` of 2000); it returns samples **out of order**, so only `locationId` identifies the input point; and it **omits** out-of-coverage points entirely rather than returning a null, which is why the result array is pre-filled with `NaN` and scattered into. It also reports errors inside a 200 body, so `raise_for_status()` alone does not detect failure. Default `sampling="nearest"` reproduces the Elevation Point Query Service bit-for-bit — `tests/test_elevation.py::UsgsApiBatchTest::test_reproduces_epqs_value` pins that, so don't change the default without re-checking published elevations.
- Filtering lives in `gradeit/filters/` under one abstraction, `ElevationFilter`. `Wood2014Filter` implements the paper's five-step routine (uniform-distance median resample → combined Savitzky-Golay + binomial → residual-threshold discard/backfill → filter again → interpolate back to the original points) and is the **default**. `BridgeFilter` is a targeted bare-earth bridge/overpass correction for spans the Wood routine declines to touch. Filters are passed to `gradeit()` via the `elevation_filter` parameter as an instance or a sequence (applied in order); grade is always recomputed from the final filtered elevation so the two stay consistent. Pass `None` (or `[]`) to disable filtering. If you use `BridgeFilter`, put it first — it keys on raw dip magnitude, which any smoother attenuates.
- Filter parameters are declared in **physical units (feet)**, not sample counts, so a filter's behavior does not change with GPS sampling rate or vehicle speed. Preserve that when adding knobs.
- `Wood2014Filter.interval_ft` must stay at or above the trace's median point spacing, or most grid nodes hold no measurement and step B stops removing noise. `min_node_occupancy` warns (`SparseGridWarning`) when that happens; it never rewrites the parameter.

## Common Commands

This project uses [pixi](https://pixi.sh) for development environments.
There is no native geospatial stack: GeoTIFFs are read with tifffile/imagecodecs, so
GDAL, rasterio and shapely are deliberately _not_ dependencies. Keep it that way — `.github/workflows/ci.yml` asserts the package installs from PyPI wheels alone.

### Running the full check (format, lint, types, tests)

```
pixi run -e dev check
```

### Running the tests

```
pixi run -e dev test
```

Formatting/linting is handled by ruff; markdown is formatted with dprint.
