# Documentation sample data

These files let documentation examples run **offline and in seconds** in CI. They do not need
downloaded USGS tiles. [`scripts/make_docs_data.py`](../../scripts/make_docs_data.py) creates these
files. Do not edit them by hand.

```
traces/golden_creek.csv   250 points, US-6 west of Golden, CO
traces/carquinez.csv      420 points, I-80 across the Carquinez Strait
tiles/n40w106/            corridor crop covering golden_creek
tiles/n39w123/            corridor crop covering carquinez
```

## These tiles are not real USGS tiles

The `.tif` names match full USGS 1/3 arc-second product names. `USGSLocal` needs this layout.
**These files are not full products.** Each file is a crop from a real tile. Data more than 500 ft
from a demo trace is the no-data sentinel. `n40w106` is 535×1060 pixels and 202 KB. The full tile
is 10812×10812 pixels and 411 MB.

`USGSLocal` returns `NaN` for a point without data. It does not raise an error. Therefore,
`USGSLocal("docs/data/tiles")` returns `NaN` elevation for traces other than these two traces.

For real work, download the real tiles with `scripts/get_usgs_tiles.py`; see
[Elevation Data](../elevation_data.md).

## Fidelity

In each retained corridor, elevation values are identical to the source data. There is no
resampling or requantization. `make_docs_data.py` checks every demo point with `USGSLocal`. It
compares the full tile and crop for `bilinear` and `nearest` sampling. Values must agree within
1e-6 ft. Documentation values also occur in the full dataset.

## Regenerating

Needs the full source tiles (`n40w106`, `n39w123`), which are not in the repository:

```bash
pixi run -e dev python scripts/make_docs_data.py \
    --source-dir /path/to/tiles
```

The `DEMOS` table at the top of the script has trace slice bounds. If you change a slice, regenerate
the data. Otherwise, the crop and trace disagree and examples return `NaN`.
