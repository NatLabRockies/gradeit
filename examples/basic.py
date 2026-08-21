# %%
from pathlib import Path

import numpy as np
import pandas as pd

from gradeit import USGSLocal, gradeit

# Resolve example data/tiles relative to this file (works from any cwd).
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# %%
example_trace = pd.read_csv(HERE / "data/sample_trip_1.csv")

# %%
example_trace.head()

# %%

# choose the elevation model;
# gradeit() defaults to USGSApi() (the online 3DEP service, no setup needed,
# batched requests), but the local raster model (USGSLocal) is faster still and
# does not depend on a public service.
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
assert result.elevation_ft_filtered is not None  # filtering ran, so these are populated
assert result.grade_dec_filtered is not None

# %%
# --- Bare-earth bridge artifacts, handled by the default --------------------
#
# The USGS DEM is a *bare-earth* model: bridge decks are not in it. Where this
# trace crosses a creek west of Golden, the raw lookup returns the streambed
# instead of the road, and differentiating that gives a grade spike no vehicle
# ever drove. Point 719 is the clearest example -- the 1 Hz trace put a single
# sample squarely on the floor of the channel.
#
# Nothing below is bridge-specific. Step D of the Wood et al. routine discards
# points whose filtration residual is large and backfills them by interpolation,
# and a bridge artifact is exactly a large residual, so the default catches it
# without being told that bridges exist.
DIP = 719

print("        raw DEM              default filter")
print(" idx    elev_ft   grade      elev_ft   grade")
for i in range(DIP - 3, DIP + 4):
    flag = "  <-- creek" if i == DIP else ""
    print(
        f" {i:4d} {result.elevation_ft_unfiltered[i]:9.2f} {100 * result.grade_dec_unfiltered[i]:7.2f}%"
        f"  {result.elevation_ft_filtered[i]:9.2f} {100 * result.grade_dec_filtered[i]:7.2f}%{flag}"
    )

deck = (result.elevation_ft_unfiltered[DIP - 1] + result.elevation_ft_unfiltered[DIP + 1]) / 2
print(
    f"\nRoad deck between the clean neighbors: {deck:.1f} ft"
    f"\n  raw      {result.elevation_ft_unfiltered[DIP]:.1f} ft "
    f"({result.elevation_ft_unfiltered[DIP] - deck:+.1f} ft) -> grade {100 * result.grade_dec_unfiltered[DIP]:+.1f}%"
    f"\n  filtered {result.elevation_ft_filtered[DIP]:.1f} ft "
    f"({result.elevation_ft_filtered[DIP] - deck:+.1f} ft) -> grade "
    f"{100 * result.grade_dec_filtered[DIP]:+.1f}%"
)

# %%
# The same story trace-wide: filtration collapses the spike tail without
# flattening the distribution, because it is removing artifacts rather than
# reshaping terrain. (The paper makes the same point -- filtration should not
# have a transformational effect on the base USGS layer.)
raw_pct = np.abs(100 * result.grade_dec_unfiltered)
filt_pct = np.abs(100 * result.grade_dec_filtered)
print(f"{'':10} {'max':>8} {'p99':>8} {'p95':>8}")
for label, g in (("raw", raw_pct), ("filtered", filt_pct)):
    print(f"{label:10} {g.max():7.2f}% {np.percentile(g, 99):7.2f}% {np.percentile(g, 95):7.2f}%")
print(
    "median |filtered - raw| elevation: "
    f"{np.median(np.abs(result.elevation_ft_filtered - result.elevation_ft_unfiltered)):.2f} ft"
)

# %%
# Materialize the result as a DataFrame for inspection/plotting (needs gradeit[pandas]).
df_w_grade = result.to_dataframe()
df_w_grade.head()

# %%
df_w_grade.elevation_ft_unfiltered.plot()
# %%
df_w_grade.elevation_ft_filtered.plot()
# %%
df_w_grade.grade_dec_unfiltered.plot()
# %%
df_w_grade.grade_dec_filtered.plot()

# %%
# The map shows "Filtered grade" and "Raw grade" as two toggleable layers, both
# visible at load with filtered drawn on top. Untick "Filtered grade" in the
# layer control to see the raw artifacts underneath -- around point 719 the raw
# layer dives deep red into the creek while the filtered layer runs level.
m = result.plot_map()

trace_html = HERE / "trace.local.html"
m.save(str(trace_html))

# %%
