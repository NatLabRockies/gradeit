## Project overview

GradeIT (Road Grade Inference Tool) is a python package that appends elevation and road grade to a sequence of GPS points, sourcing elevation from the USGS Digital Elevation Model.

## Architecture

The public API is the top-level package: `from gradeit import gradeit, GradeResult, Source, SavitzkyGolayFilter, BridgeGradeFilter, ...` (see `gradeit/__init__.py`). The orchestration lives in `gradeit/_core.py`.

- `gradeit()` accepts flexible input (DataFrame / numpy `(n,2)` / dict / iterable of `Coordinate` or `(lat, lon)`) via `gradeit/io.py:to_coordinates`, and returns a pandas-free `GradeResult` (numpy arrays + `.to_dataframe()` / `.to_dict()`). It never mutates its input. pandas is an optional dependency, imported lazily only in `GradeResult.to_dataframe()`.
- Elevation sources live under `gradeit/elevation/`; `gradeit/sources.py` maps the `Source` enum / legacy strings to a model. Custom `ElevationModel` instances can be injected.
- Filtering lives in `gradeit/filters/`, with two parallel concepts: `ElevationFilter` smooths elevation _before_ grade (`SavitzkyGolayFilter`); `GradeFilter` corrects grade _after_ (`BridgeGradeFilter`). Both are injected into `gradeit()` as instances or `True`.

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
