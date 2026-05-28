# %%
from pathlib import Path

import pandas as pd

from gradeit import BridgeFilter, SavitzkyGolayFilter, USGSLocal, gradeit

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
elevation_model = USGSLocal(db_path)

# %%
# gradeit accepts a DataFrame (or arrays / lists / dicts) and returns a GradeResult.
# Pass a list of ElevationFilters to apply in order: BridgeFilter first
# interpolates elevation across bare-earth bridge artifacts, then
# SavitzkyGolayFilter smooths the cleaned profile.
result = gradeit(
    example_trace,
    elevation_model=elevation_model,
    elevation_filter=[BridgeFilter(), SavitzkyGolayFilter()],
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

trace_html = HERE / "trace.html"
m.save(str(trace_html))

# %%
