## Project overview

GradeIT (Road Grade Inference Tool) is a python package that appends elevation and road grade to a sequence of GPS points, sourcing elevation from the USGS Digital Elevation Model.

## Architecture

The public API is the top-level package: `from gradeit import gradeit, GradeResult, USGSApi, USGSLocal, SavitzkyGolayFilter, BridgeFilter, ...` (see `gradeit/__init__.py`). The orchestration lives in `gradeit/core.py`.

- `gradeit()` accepts flexible input (DataFrame / numpy `(n,2)` / dict / iterable of `Coordinate` or `(lat, lon)`) via `gradeit/io.py:to_coordinates`, and returns a pandas-free `GradeResult` (numpy arrays + `.to_dataframe()` / `.to_dict()`). It never mutates its input. pandas is an optional dependency, imported lazily only in `GradeResult.to_dataframe()`.
- Elevation comes from an `ElevationModel` (under `gradeit/elevation/`), passed via the `elevation_model` parameter. It defaults to `USGSApi()` (the online query service); `USGSLocal(path)` reads local raster tiles. There is no separate "source" concept — callers construct and pass the model directly. `requests` (used by `USGSApi`) is a core dependency but is imported lazily so `import gradeit` stays cheap.
- Filtering lives in `gradeit/filters/` under one abstraction, `ElevationFilter`: `BridgeFilter` linearly interpolates elevation across bare-earth-DEM bridge artifacts, `SavitzkyGolayFilter` smooths the elevation profile. They are passed to `gradeit()` via the `elevation_filter` parameter as an instance or a sequence (applied in order); grade is always recomputed from the final filtered elevation so the two stay consistent. `elevation_filter` defaults to a single `BridgeFilter()`; pass `None` (or `[]`) to disable filtering. Recommended order for noisy data: `[BridgeFilter(), SavitzkyGolayFilter()]`.

## Common Commands

This project uses [pixi](https://pixi.sh) for development environments.
The native geospatial stack (rasterio/GDAL, shapely) comes from conda-forge.

### Running the full check (format, lint, types, tests)

```
pixi run -e dev check
```

### Running the tests

```
pixi run -e dev test
```

Formatting/linting is handled by ruff; markdown is formatted with dprint.
