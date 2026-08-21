# Elevation Data

The `elevation_model` argument selects an `ElevationModel`. GradeIT has two built-in models.

## `USGSApi` — the online query service

```python
from gradeit import USGSApi, gradeit

result = gradeit(trace, elevation_model=USGSApi())  # this is the default
```

`USGSApi` queries the USGS [3D Elevation Program](https://www.usgs.gov/3d-elevation-program) (3DEP)
bare-earth service. It doesn't require any setup. Points are sent in batches of up to 1,000 per
request, so a trace costs a handful of requests rather than one per point. The values are identical
to the [Elevation Point Query Service](https://epqs.nationalmap.gov/v1/), which is a single-point
wrapper over the same data.

Batching makes the online model usable for whole traces: a 2,500-point trace takes about six seconds.
`USGSLocal` is still faster and doesn't depend on a public service, so prefer it for repeated or
bulk work. Take a look at [Downloading USGS Tiles](#getting-the-tiles) for instructions on how to
get the local DEM tiles.

### Options

```python
USGSApi(
    batch_size=1000,  # points per request; capped at the service limit of 1000
    sampling="nearest",  # or "bilinear"
    timeout=60.0,  # seconds per request
    max_retries=3,  # attempts per batch on timeout or a 429/5xx response
)
```

`sampling="nearest"` returns the cell containing the point, which is what the Elevation Point Query
Service returns. `sampling="bilinear"` asks the service to interpolate the surrounding cells,
matching the default of `USGSLocal`. Note that the two models therefore differ by default; pass the
same `sampling` to both if you compare them.

### Missing data

Points outside the service's coverage return **`NaN`**, the same as `USGSLocal`. The service omits
those points from its response rather than reporting an error.

## `USGSLocal` — local raster tiles

```python
from gradeit import USGSLocal, gradeit

result = gradeit(
    trace,
    elevation_model=USGSLocal("path/to/tiles", sampling="bilinear"),
)
```

`USGSLocal` reads the DEM from disk. It groups points by tile and opens each tile once. This makes
full-trace lookups fast.

### Directory layout

`USGSLocal` needs the directory layout from the download script:

```
tiles/
├── n40w105/USGS_13_n40w105.tif
├── n40w106/USGS_13_n40w106.tif
└── n41w105/USGS_13_n41w105.tif
```

Tile names identify the **northwest corner** of a 1°×1° cell. `n40w105` covers latitude 39–40 and
longitude −105 to −104. A point at 39.7 N, 105.2 W is in `n40w106`, not `n40w105`. GradeIT
calculates tile names. You need this information only when you select tiles to download.

The dataset supports only the northern and western hemispheres.

### Sampling

```python
USGSLocal(path, sampling="bilinear")  # default
USGSLocal(path, sampling="nearest")
```

`bilinear` interpolates the four nearby cells. `nearest` returns the cell that contains the point.
Both methods use pixel centers. `bilinear` returns the exact pixel value at a pixel center.

### Missing data

Points outside the available tiles and points over DEM void cells return **`NaN`**. GradeIT does not
raise an error or use a sentinel value. GradeIT raises `FileNotFoundError` if a required tile is not
in the directory.

If every point returns `NaN`, you may have the correct directory and incorrect tiles. Check the
grid reference for the first coordinate.

## Getting the tiles

The 1/3 arc-second dataset covers the conterminous United States. It has about 33 ft (10 m) post
spacing and a stated vertical RMSE of 2.44 m. It is a **bare-earth** product. See
[Methodology](methodology) for why that matters. Browse it at the
[USGS staged products index](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/13/TIFF/current/).

This repository ships a download script:

```bash
python scripts/get_usgs_tiles.py --output-dir path/to/tiles/
```

Flags:

- `--output-dir` — where to write tiles. Defaults to `usgs_tiles/`.
- `--tile-data` — a text file listing tile names, one per line. Defaults to
  `scripts/usgs_tiles.txt`, which is all 1,432 CONUS tiles.
- `--nprocs` — parallel downloads. Defaults to 4.

### Budget the disk first

Each tile needs **220–490 MB**. The full CONUS set needs more than 400 GB. Download only tiles that
cover your traces:

```bash
# Colorado only, using the bundled tile list (~14 GB)
python scripts/get_usgs_tiles.py \
    --tile-data scripts/colorado_tiles.txt \
    --output-dir colorado_tiles/ \
    --nprocs 8

# Or name specific tiles
printf 'n38w123\nn39w123\n' > sf_tiles.txt
python scripts/get_usgs_tiles.py --tile-data sf_tiles.txt --output-dir sf_tiles/
```

## Something else entirely

`ElevationModel` can be customized. You can use another DEM, a lidar survey, a database, or a vendor
API. See
[Custom Elevation Sources](examples/05_custom_elevation_model_example).
