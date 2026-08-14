# %%
from pathlib import Path

import pandas as pd

from gradeit import BridgeFilter, USGSLocal, Wood2014Filter, gradeit

# Resolve example data/tiles relative to this file (works from any cwd).
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# %%
example_trace = pd.read_csv(HERE / "data/sample_trip_1.csv")

# %%
example_trace.head()

# %%

# choose the elevation model;
# gradeit() defaults to USGSApi() (the online query service, no setup needed),
# but for whole-trace lookups the local raster model (USGSLocal) is much faster.
# USGSLocal requires you download the USGS raster tiles; see the
# scripts/get_usgs_tiles.py script. Sample traces 1, 2, and 3 are in Colorado,
# so you can use the colorado_tiles.txt file as an input to the script.
db_path = REPO_ROOT / "scripts/colorado_tiles"
if not db_path.is_dir():
    raise SystemExit(
        f"No USGS tiles at {db_path}.\n"
        "Download them first (~14 GB for all of Colorado, or edit the tile list down):\n"
        "    python scripts/get_usgs_tiles.py "
        "--tile-data scripts/colorado_tiles.txt --output-dir scripts/colorado_tiles\n"
        "Or point db_path at a directory you already have."
    )
elevation_model = USGSLocal(db_path)

# %%
# gradeit accepts a DataFrame (or arrays / lists / dicts) and returns a GradeResult.
# With no elevation_filter argument it applies Wood2014Filter, the filtration
# routine from Wood et al. (2014) -- that is all most callers need:
result = gradeit(example_trace, elevation_model=elevation_model)

# %%
# Filters can also be passed explicitly, as an instance or a sequence applied in
# order. BridgeFilter goes first when used: it keys on raw dip magnitude, which
# any smoother attenuates. It catches bridge spans longer than Wood2014Filter's
# outlier rejection will accept.
result = gradeit(
    example_trace,
    elevation_model=elevation_model,
    elevation_filter=[BridgeFilter(), Wood2014Filter()],
)

# %%
# Materialize the result as a DataFrame for inspection/plotting (needs gradeit[pandas]).
df_w_grade = result.to_dataframe()
df_w_grade.head()

# %%
df_w_grade.elevation_ft.plot()
# %%
df_w_grade.elevation_ft_filtered.plot()
# %%
df_w_grade.grade_dec_unfiltered.plot()
# %%
df_w_grade.grade_dec_filtered.plot()

# %%
m = result.plot_map()

trace_html = HERE / "trace.local.html"
m.save(str(trace_html))

# %%
