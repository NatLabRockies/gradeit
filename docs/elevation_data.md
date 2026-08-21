# Elevation Data

The `elevation_model` argument selects an `ElevationModel`. GradeIT has two built-in models.

## `USGSApi` — the online query service

```python
from gradeit import USGSApi, gradeit

result = gradeit(trace, elevation_model=USGSApi())  # this is the default
```

`USGSApi` queries the USGS [Elevation Point Query Service](https://epqs.nationalmap.gov/v1/). It
needs no setup, disk space, or downloads. It sends one HTTP request for each point.

Use `USGSApi` to check a few coordinates. Do not use it for a full trace. A 1,400-point trace needs
1,400 requests. The service can be unavailable or rate-limited. Use `USGSLocal` for full traces.

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

## What this site's examples use

The examples on this site do not download data. They use small crops of two real tiles in
`docs/data/tiles/`. The crops cover narrow corridors around two short traces. They need 440 KB
instead of 900 MB.

Inside these corridors, values are identical to the full dataset. Outside these corridors, the
tiles have no data. `USGSLocal("docs/data/tiles")` returns `NaN` for other traces. See
[`docs/data/README.md`](https://github.com/NREL/gradeit/blob/main/docs/data/README.md) for
details and `scripts/make_docs_data.py` for how they were produced.

## Something else entirely

`ElevationModel` has one method. You can use another DEM, a lidar survey, a database, or a vendor
API. See
[Custom Elevation Sources](examples/05_custom_elevation_model_example).
