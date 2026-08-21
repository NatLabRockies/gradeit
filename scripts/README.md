# Scripts

## Download tiles

`get_usgs_tiles.py` downloads the raster tiles that GradeIT uses for elevation data.

### Usage

The script accepts these optional arguments:

- `--output-dir`: Directory for the tiles. The default is `usgs_tiles/`.
- `--tile-data`: File that lists the tiles to download. The default is `usgs_tiles.txt`.
- `--nprocs`: Number of download processes. The default is 4.

### Example

This command downloads tiles that cover Colorado. It uses `colorado_tiles.txt`:

```console
python get_usgs_tiles.py --output-dir colorado_tiles/ --tile-data colorado_tiles.txt --nprocs 2
```
