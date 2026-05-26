## Project overview

GradeIT (Road Grade Inference Tool) is a python package that appends elevation and road grade to a sequence of GPS points, sourcing elevation from the USGS Digital Elevation Model.

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
