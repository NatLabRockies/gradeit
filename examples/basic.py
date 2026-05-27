# %%
from pathlib import Path

import pandas as pd

from gradeit import BridgeGradeFilter, gradeit

# Resolve example data/tiles relative to this file (works from any cwd).
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# %%
example_trace = pd.read_csv(HERE / "data/sample_trip_1.csv")

# %%
example_trace.head()

# %%

# choose source for elevation data;
# the usgs-local option requires you download the USGS raster tiles;
# see the scripts/get_usgs_tiles.py script to download tiles;
# sample traces 1, 2, and 3 are in the state of Colorado and so you can use the colorado_tiles.txt
# file as an input to the script

source = "usgs-local"  # options: 'usgs-api', 'usgs-local'

# if using the usgs-local option, you must provide the path to the local raster tiles
db_path = REPO_ROOT / "scripts/colorado_tiles"

# %%
# gradeit accepts a DataFrame (or arrays / lists / dicts) and returns a GradeResult.
# elevation_filter=True smooths the elevation profile before computing grade;
# pass a BridgeGradeFilter as grade_filter to also correct bare-earth bridge artifacts.
result = gradeit(
    example_trace,
    source=source,
    usgs_db_path=db_path,
    elevation_filter=True,
    grade_filter=BridgeGradeFilter(),
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
