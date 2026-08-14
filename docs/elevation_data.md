# Elevation Data

Elevation enters GradeIT through an `ElevationModel`, chosen with the `elevation_model` argument.
Two are built in.

## `USGSApi` — the online query service

```python
from gradeit import USGSApi, gradeit

result = gradeit(trace, elevation_model=USGSApi())  # this is the default
```

Queries the USGS [Elevation Point Query Service](https://epqs.nationalmap.gov/v1/). No setup, no
disk, no downloads — and one HTTP request **per point**, issued serially.

That makes it a good way to check a handful of coordinates and a bad way to process a trace: a
1,400-point trip is 1,400 round trips. It is also subject to the service being up and to whatever
rate limiting it applies. Use it for spot checks; use `USGSLocal` for work.

## `USGSLocal` — local raster tiles

```python
from gradeit import USGSLocal, gradeit

result = gradeit(
    trace,
    elevation_model=USGSLocal("path/to/tiles", sampling="bilinear"),
)
```

Reads the DEM directly off disk. Points are grouped by the tile that contains them so each tile is
opened once, which makes whole-trace lookups fast.

### Directory layout

`USGSLocal` expects the layout the download script produces:

```
tiles/
├── n40w105/USGS_13_n40w105.tif
├── n40w106/USGS_13_n40w106.tif
└── n41w105/USGS_13_n41w105.tif
```

Tile names encode the **northwest corner** of a 1°×1° cell: `n40w105` covers latitude 39–40 and
longitude −105 to −104. A point at 39.7 N, 105.2 W is therefore in `n40w106`, not `n40w105` — the
off-by-one trips people up. GradeIT computes the name for you; you only need it when deciding
which tiles to download.

Only the northern and western hemispheres are supported, matching the coverage of the dataset.

### Sampling

```python
USGSLocal(path, sampling="bilinear")  # default
USGSLocal(path, sampling="nearest")
```

`bilinear` interpolates the four surrounding cells and is smoother; `nearest` returns the
containing cell. Both are registered on pixel centers, so bilinear sampling at a pixel's own
center returns that pixel's value exactly.

### Missing data

Points outside the available tiles, and points over DEM void cells, come back as **`NaN`** —
GradeIT does not raise and does not substitute a sentinel. If a tile a point needs is missing
from the directory entirely, that _does_ raise `FileNotFoundError`.

The practical consequence: if a whole trace comes back `NaN`, you probably have the right
directory but the wrong tiles. Check the grid reference of your first coordinate.

## Getting the tiles

The 1/3 arc-second dataset is continuous for the conterminous United States, with roughly 33 ft
(10 m) post spacing and a stated vertical RMSE of 2.44 m. It is a **bare-earth** product — see
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

Individual tiles run **220–490 MB**. The full CONUS set is well over 400 GB. Download only what
your traces cover:

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

The examples on this site do not download anything. They read small crops of two real tiles,
committed under `docs/data/tiles/`, covering narrow corridors around two short demo traces —
440 KB in total, in place of 900 MB.

Within those corridors the values are bit-for-bit identical to the full dataset, so the numbers
the examples print are real. Outside them the tiles are no-data, which means pointing
`USGSLocal("docs/data/tiles")` at any other trace returns `NaN`. See
[`docs/data/README.md`](https://github.com/NREL/gradeit/blob/main/docs/data/README.md) for
details and `scripts/make_docs_data.py` for how they were produced.

## Something else entirely

`ElevationModel` is a one-method interface, so a different DEM, a lidar survey, a database, or a
vendor API all plug in the same way. See
[Custom Elevation Sources](examples/05_custom_elevation_model_example).
