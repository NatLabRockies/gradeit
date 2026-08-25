# %%
"""When `BridgeFilter` earns its place, on real data.

`docs/examples/02_filtering_example.py` shows the default `Wood2014Filter` cleanly
removing a creek-crossing artifact near Golden, CO with no configuration -- and
stock `BridgeFilter` making that same trace much worse. That invites an obvious
question: is `BridgeFilter` worth keeping at all?

It is, and this trace shows why. `SF_bridge_trip_segment.csv` runs 65 miles up
the east side of San Francisco Bay and crosses **two** bare-earth artifacts that
sit on opposite sides of the default filter's competence:

* an ~800 ft crossing, which the default removes by itself, and
* the Carquinez Strait crossing on I-80 -- 5,332 ft of open water, where the
  bare-earth DEM returns the water surface ~166 ft below the deck.

The reason the default cannot reach the second one is structural, not a matter
of tuning. `Wood2014Filter` detects artifacts by **filtration residual**: it
smooths the profile and flags points far from their own smoothed version. That
detector is blind to any feature wider than its own smoothing kernel, because
the smoother simply follows a wide feature down and the residual collapses.
`BridgeFilter` instead compares each point against a two-sided **rolling-max
baseline** -- an absolute comparison against surrounding high ground -- which
reaches spans the residual method structurally cannot.

Tiles: this trace needs ``n38w123`` and ``n39w123`` (~705 MB together)::

    printf 'n38w123\\nn39w123\\n' > sf_tiles.txt
    python scripts/get_usgs_tiles.py --tile-data sf_tiles.txt --output-dir sf_tiles

Then run with ``GRADEIT_TILES=sf_tiles python examples/bridge_filter_long_spans.py``.
"""

import csv
import os
from pathlib import Path

import numpy as np

from gradeit import USGSLocal, gradeit
from gradeit.filters import BridgeFilter, Wood2014Filter

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# The two artifacts, as (first, last) index of the bad run. Verified below.
BRIDGES: dict[str, tuple[int, int]] = {
    "short crossing": (4113, 4119),
    "Carquinez Strait": (4312, 4376),
}

# %%
db_path = Path(os.environ.get("GRADEIT_TILES", REPO_ROOT / "sf_tiles"))
if not db_path.is_dir():
    raise SystemExit(
        f"No USGS tiles at {db_path}.\n"
        "This trace needs n38w123 and n39w123 (~705 MB):\n"
        "    printf 'n38w123\\nn39w123\\n' > sf_tiles.txt\n"
        "    python scripts/get_usgs_tiles.py --tile-data sf_tiles.txt --output-dir sf_tiles\n"
        "Then set GRADEIT_TILES=/path/to/tiles."
    )
elevation_model = USGSLocal(db_path)

with (HERE / "data/SF_bridge_trip_segment.csv").open() as handle:
    trace = [(float(r["latitude"]), float(r["longitude"])) for r in csv.DictReader(handle)]

raw = gradeit(trace, elevation_model=elevation_model, elevation_filter=None)
cum_ft = np.cumsum(raw.distances_ft)


def deck(start: int, stop: int) -> np.ndarray:
    """The road deck across a span: linear between the clean anchors on each side.

    The real deck is not exactly linear, but both approaches here sit within a
    few feet of the same elevation, so this is a fair reference for "how far is
    the filtered profile from the road".
    """
    return np.interp(
        cum_ft[start : stop + 1],
        [cum_ft[start - 1], cum_ft[stop + 1]],
        [raw.elevation_ft_unfiltered[start - 1], raw.elevation_ft_unfiltered[stop + 1]],
    )


def error_on(start: int, stop: int, elevation: np.ndarray) -> float:
    """Max feet by which a profile misses the road deck across the span."""
    return float(np.abs(elevation[start : stop + 1] - deck(start, stop)).max())


# %%
# --- 1. The two artifacts ---------------------------------------------------
print(f"{len(trace)} points, {cum_ft[-1] / 5280:.1f} mi\n")
print(f"  {'':18} {'span_ft':>8} {'depth_ft':>9} {'aspect':>7}  location")
for name, (s, t) in BRIDGES.items():
    span = float(cum_ft[t + 1] - cum_ft[s - 1])
    depth = float((deck(s, t) - raw.elevation_ft_unfiltered[s : t + 1]).max())
    mid = (s + t) // 2
    print(
        f"  {name:18} {span:8.0f} {depth:9.1f} {span / depth:7.1f}"
        f"  {trace[mid][0]:.4f}, {trace[mid][1]:.4f}"
    )

s, t = BRIDGES["Carquinez Strait"]
print(
    f"\nRaw profile across the Carquinez Strait (deck ~{raw.elevation_ft_unfiltered[s - 1]:.0f} ft):\n"
)
print("   idx    elev_ft   grade%")
for i in range(s - 3, t + 4, 8):
    print(
        f"  {i:5d} {raw.elevation_ft_unfiltered[i]:9.1f} {100 * raw.grade_dec_unfiltered[i]:8.2f}"
    )
print(
    f"\nThe DEM sits on the water for {cum_ft[t] - cum_ft[s]:.0f} ft at ~"
    f"{raw.elevation_ft_unfiltered[s : t + 1].min():.1f} ft elevation, so the trace 'descends' "
    f"{100 * raw.grade_dec_unfiltered[s : t + 2].min():.0f}%\ninto the strait and 'climbs' "
    f"{100 * raw.grade_dec_unfiltered[s : t + 2].max():+.0f}% out of it."
)

# %%
# --- 2. What the default does to each ---------------------------------------
#
# Nothing here is bridge-specific: step D of the Wood et al. routine discards
# points with a large filtration residual and backfills them. That is enough for
# the short crossing and not enough for the long one.
default = gradeit(trace, elevation_model=elevation_model)
assert default.elevation_ft_filtered is not None
assert default.grade_dec_filtered is not None

print("Max error against the road deck, in feet:\n")
print(f"  {'':18} {'raw DEM':>10} {'Wood2014Filter()':>18}")
for name, (bs, bt) in BRIDGES.items():
    print(
        f"  {name:18} {error_on(bs, bt, raw.elevation_ft_unfiltered):10.1f}"
        f" {error_on(bs, bt, default.elevation_ft_filtered):18.1f}"
    )
print(
    "\nThe short crossing is removed outright. The long one is untouched -- the"
    "\nsmoother follows the profile down onto the water, so there is no residual"
    "\nto flag and nothing gets discarded."
)

# %%
# --- 3. Widening the smoothing window does not rescue it --------------------
#
# It is tempting to assume the fix is a wider savgol_window_ft, since the window
# is what bounds the detector's reach. On a synthetic straight ramp that works.
# On real terrain it does not: a wider window also makes the smoothed reference
# a worse fit to genuine curvature, so the residual degrades instead of
# improving -- and the short crossing that used to work stops working.
print("Max error on each bridge vs savgol_window_ft (feet):\n")
print(f"  {'window_ft':>10} {'short':>9} {'Carquinez':>11}")
for window_ft in (600.0, 1200.0, 2400.0, 4800.0, 9600.0):
    tuned = gradeit(
        trace,
        elevation_model=elevation_model,
        elevation_filter=Wood2014Filter(savgol_window_ft=window_ft),
    )
    assert tuned.elevation_ft_filtered is not None
    cells = [error_on(bs, bt, tuned.elevation_ft_filtered) for bs, bt in BRIDGES.values()]
    print(f"  {window_ft:10.0f} {cells[0]:9.1f} {cells[1]:11.1f}")
print(
    "\nNo setting covers both. This is the gap BridgeFilter exists to fill --"
    "\nnot a convenience that retuning the default could replace."
)

# %%
# --- 4. BridgeFilter reaches it, if the radius clears the span --------------
#
# The rolling-max baseline has to find real road at deck height on both sides,
# and the approach ramps are themselves below deck. In practice that means
# baseline_radius_ft must be roughly the *full* span, not half of it.
print(f"Carquinez span is {cum_ft[t + 1] - cum_ft[s - 1]:.0f} ft.\n")
print(f"  {'radius_ft':>10} {'err_ft':>8} {'max|grade|':>11} {'p99|grade|':>11}")
for radius in (2640.0, 4000.0, 5280.0, 9000.0):
    fixed = gradeit(
        trace,
        elevation_model=elevation_model,
        elevation_filter=[BridgeFilter(baseline_radius_ft=radius), Wood2014Filter()],
    )
    assert fixed.elevation_ft_filtered is not None
    assert fixed.grade_dec_filtered is not None
    g = np.abs(100 * fixed.grade_dec_filtered)
    print(
        f"  {radius:10.0f} {error_on(s, t, fixed.elevation_ft_filtered):8.1f}"
        f" {g.max():10.1f}% {np.percentile(g, 99):10.2f}%"
    )

# %%
# --- 5. The recommended pipeline --------------------------------------------
#
# BridgeFilter first (it keys on raw dip magnitude, which any smoother
# attenuates), then the default routine over the corrected profile.
best = gradeit(
    trace,
    elevation_model=elevation_model,
    elevation_filter=[BridgeFilter(baseline_radius_ft=6000.0), Wood2014Filter()],
)
assert best.elevation_ft_filtered is not None
assert best.grade_dec_filtered is not None

print(f"  {'':34} {'short':>8} {'Carquinez':>11} {'max|g|':>9} {'p99|g|':>9}")
for label, elev, grade in (
    ("raw DEM", raw.elevation_ft_unfiltered, raw.grade_dec_unfiltered),
    ("Wood2014Filter()  [default]", default.elevation_ft_filtered, default.grade_dec_filtered),
    ("BridgeFilter(6000) + Wood2014", best.elevation_ft_filtered, best.grade_dec_filtered),
):
    g = np.abs(100 * grade)
    ss, st = BRIDGES["short crossing"]
    print(
        f"  {label:34} {error_on(ss, st, elev):7.1f} {error_on(s, t, elev):10.1f}"
        f" {g.max():8.1f}% {np.percentile(g, 99):8.2f}%"
    )

# %%
# --- 6. Why the same filter wrecked the Denver trace ------------------------
print(
    """
Note what changed between this trace and docs/examples/02_filtering_example.py: nothing
about the filter. The stock one-mile baseline_radius_ft works here and fails
badly there, because the radius has to satisfy two conflicting constraints at
once --

    wide enough to clear the bridge span,
    narrow enough not to reach over the surrounding terrain's own relief.

At Carquinez the span is long but the terrain beyond the approaches is flat, so
a mile satisfies both. Near Golden the bridge is a 275 ft creek crossing sitting
inside a mile-wide, 172 ft deep real valley -- a mile-wide window sees the
valley, calls it one enormous bridge, and interpolates a flat line across it.

There is no default that is right for both. That is why baseline_radius_ft is
the parameter to set deliberately, from the spans you actually need to fix.

When to reach for BridgeFilter
------------------------------
  1. Your traces contain bridge spans longer than roughly savgol_window_ft
     (~600 ft by default). Shorter spans need nothing extra.
  2. The span is deep relative to its length -- span / depth under
     max_aspect_ratio (50). Long shallow crossings are rejected by design,
     because they are not distinguishable from valleys.
  3. A radius exists that clears the span without reaching over nearby terrain
     relief. Sweep it as in section 4 and check both ends.
  4. Always diff the filtered profile against the raw one across the *whole*
     trace, not just at the bridge: this filter fails by silently flattening
     real terrain, which is much harder to spot than the artifact it removes.
"""
)

# %%
# --- 7. Look at it ----------------------------------------------------------
import matplotlib.pyplot as plt

window = slice(s - 120, t + 120)
miles = cum_ft / 5280.0
fig, (ax_e, ax_g) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

ax_e.plot(miles[window], raw.elevation_ft_unfiltered[window], lw=1.0, color="0.6", label="Raw USGS")
ax_e.plot(
    miles[window],
    default.elevation_ft_filtered[window],
    lw=1.4,
    color="C1",
    label="Wood2014Filter() only",
)
ax_e.plot(
    miles[window],
    best.elevation_ft_filtered[window],
    lw=1.6,
    color="C0",
    label="BridgeFilter + Wood2014",
)
ax_e.set_ylabel("Elevation, ft")
ax_e.legend(loc="lower right")
ax_e.grid(alpha=0.3)

ax_g.plot(
    miles[window], 100 * raw.grade_dec_unfiltered[window], lw=1.0, color="0.6", label="Raw USGS"
)
ax_g.plot(
    miles[window],
    100 * default.grade_dec_filtered[window],
    lw=1.4,
    color="C1",
    label="Default only",
)
ax_g.plot(
    miles[window],
    100 * best.grade_dec_filtered[window],
    lw=1.6,
    color="C0",
    label="BridgeFilter + Wood2014",
)
ax_g.axhline(0, lw=0.8, color="k")
ax_g.set_ylabel("Road grade, %")
ax_g.set_xlabel("Distance, mi")
ax_g.legend(loc="upper right")
ax_g.grid(alpha=0.3)

fig.suptitle("Carquinez Strait crossing: a 5,332 ft bare-earth bridge artifact")
fig.tight_layout()
out_png = HERE / "carquinez.local.png"
fig.savefig(out_png, dpi=150)
print(f"wrote {out_png}")

# %%
