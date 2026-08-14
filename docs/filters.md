# Filters

Raw DEM elevation profiles carry outliers and unrealistic topography — spatial noise in the GPS
track, the 1/3 arc-second resolution of the model, and bare-earth artifacts where the road is on
a structure. GradeIT cleans the profile with one or more `ElevationFilter`s before grade is
computed.

```python
from gradeit import BridgeFilter, Wood2014Filter, gradeit

gradeit(trace, elevation_model=model)  # Wood2014Filter, the default
gradeit(trace, elevation_model=model, elevation_filter=None)  # no filtering
gradeit(trace, elevation_model=model, elevation_filter=Wood2014Filter(savgol_window_ft=1200))
gradeit(
    trace,
    elevation_model=model,
    elevation_filter=[BridgeFilter(baseline_radius_ft=6000), Wood2014Filter()],
)
```

Sequences apply in order, each filter consuming the previous one's output. Grade is always
recomputed from the final elevation. All parameters are in **feet**.

## `Wood2014Filter` — the default

Implements steps B–E of [the Wood et al. routine](methodology): resample onto a uniform distance
grid, smooth, discard and backfill anomalous nodes, smooth again, interpolate back.

This is what you get when you pass nothing, and for most traces it is all you need — including
for ordinary bridges and overpasses, which it removes without any bridge-specific logic.

| Parameter               | Default  | What it controls                                                                                                                   |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `interval_ft`           | `100.0`  | Uniform distance-grid spacing (step B). ~3× the DEM's 33 ft post spacing; below one post, adjacent nodes read the same cell.       |
| `savgol_window_ft`      | `600.0`  | Savitzky-Golay width. Wider means a smoother grade signal and more attenuation of short real features.                             |
| `savgol_polyorder`      | `3`      | Polynomial order within the window.                                                                                                |
| `binomial_sigma_ft`     | `100.0`  | Binomial stage width, as a Gaussian-equivalent sigma.                                                                              |
| `residual_threshold_ft` | `8.0`    | Step D discard threshold on \|pre − post\|. Equals the DEM's 2.44 m vertical RMSE.                                                 |
| `residual_grow_ratio`   | `0.5`    | Hysteresis: a run above `threshold × ratio` is discarded whole if any node breaches the full threshold. Set to `1.0` to disable.   |
| `max_discard_len_ft`    | `2000.0` | Runs longer than this are treated as real topography, not artifacts.                                                               |
| `max_discard_fraction`  | `0.25`   | Safety valve so unusually noisy input cannot silently erase a quarter of the trace.                                                |
| `max_gap_ft`            | `1000.0` | Unobserved stretches longer than this split the trace into independently filtered segments; points inside such a gap return `NaN`. |

It is a frozen dataclass, so every knob is a constructor argument and instances are safe to share.

### Tuning notes

**`savgol_window_ft`** is the smoothness dial. Widening it lowers grade noise but attenuates
genuine short features, and on a trace with a wide bare-earth artifact it will drag the road
_toward_ the artifact rather than lifting it out.

**`residual_threshold_ft`** decides what counts as an artifact. Lower rejects more aggressively.
Raising it past roughly twice the default stops catching real artifacts —
[a worked sweep](examples/02_filtering_example) shows a creek crossing surviving filtration at
16 ft.

**`residual_grow_ratio`** exists because a wide artifact drags the smoothed curve down with it,
shrinking the residual in the middle of the artifact. Without hysteresis a per-node test punches
out the flanks and leaves the floor.

`resolve_parameters()` reports what your feet resolve to in samples on a given trace, without
running the filter:

```python
from gradeit.filters.wood2014 import resolve_parameters

delta_ft, window, polyorder, binomial_order = resolve_parameters(Wood2014Filter(), total_ft)
```

## `BridgeFilter` — targeted bare-earth correction

Detects dips that sit below the surrounding road on **both** sides and interpolates the road's
elevation across them, effectively building the bridge the DEM is missing.

The detector compares each point against a baseline built from the rolling **maximum** of
elevation in a window on each side, taking the minimum of the two side-maxima. That construction
makes the baseline collapse to the point's own elevation on a steady climb or descent, so uniform
grade does not trigger false positives — only a genuine dip does.

Because it compares against surrounding high ground rather than against a smoothed version of the
signal, it reaches spans that `Wood2014Filter`'s residual test structurally cannot.

| Parameter                | Default           | What it controls                                                                                                                  |
| ------------------------ | ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `baseline_radius_ft`     | `5280.0` (1 mi)   | Half-width of the rolling-max window on each side. **This is the parameter to tune.**                                             |
| `min_dip_depth_ft`       | `5.0`             | Per-point threshold for inclusion in a candidate dip.                                                                             |
| `min_peak_depth_ft`      | `10.0`            | At least one point in a run must reach this depth. Filters out wide, shallow noise.                                               |
| `min_bridge_len_ft`      | `50.0`            | Minimum accepted span. Shorter runs are usually noise.                                                                            |
| `max_bridge_len_ft`      | `7920.0` (1.5 mi) | Maximum accepted span. Longer runs are usually real terrain.                                                                      |
| `max_aspect_ratio`       | `50.0`            | Reject runs whose span ÷ peak depth exceeds this. Bridges are short relative to their depth; valleys are long relative to theirs. |
| `grade_plausibility_tol` | `0.05`            | Reject a correction whose recovered grade differs from the surrounding median segment grade by more than this.                    |

```{warning}
**A real valley is also a span that sits below the road on both sides.** Nothing in the geometry
distinguishes the two, and the acceptance gates above cannot save you — a deep valley genuinely
is short relative to its depth.

`baseline_radius_ft` is what draws the line, and its one-mile default is only right for gentle
terrain. Scale it to the spans you are actually correcting: a few hundred feet for typical
overpasses and creek crossings, a few thousand for a major water crossing. Too wide, and a
genuine descent into a valley and climb back out reads as one enormous dip that the filter will
happily interpolate a straight line across.
```

Two worked examples cover both directions of that failure:

- [How Filtration Works](examples/02_filtering_example) — the one-mile default flattening 1.5
  miles of real Colorado canyon by up to 130 ft, on a trace the default `Wood2014Filter` handles
  perfectly.
- [Bare-Earth Bridges](examples/03_bridges_example) — a 5,332 ft crossing of the Carquinez Strait
  that `Wood2014Filter` cannot touch at any setting, cleared once `baseline_radius_ft` covers the
  span.

**Order matters.** If you use `BridgeFilter`, put it first in the sequence: it keys on raw dip
magnitude, which any smoother attenuates.

## `SavitzkyGolayFilter` — legacy

```python
SavitzkyGolayFilter(window=17, polyorder=3)
```

Smooths in the **index** domain — over the ordered sequence of points, not over distance. Because
GPS traces are sampled in time, a fixed point-count window has a physical width that varies with
vehicle speed, which is precisely the problem step B of the Wood routine exists to solve.

Superseded by `Wood2014Filter` for essentially all uses; retained for backward compatibility.
`window=0` selects a default sized from the trace's cumulative distance.

## Writing your own

`ElevationFilter` requires one method:

```python
from typing import List

from gradeit import Coordinate, ElevationFilter


class ClampFilter(ElevationFilter):
    """Clip elevation to a plausible range."""

    def __init__(self, min_ft: float, max_ft: float):
        self.min_ft = min_ft
        self.max_ft = max_ft

    def filter(
        self,
        elevation_profile: List[float],
        coordinates: List[Coordinate],
    ) -> List[float]:
        return [min(max(e, self.min_ft), self.max_ft) for e in elevation_profile]
```

Take an elevation profile, return an elevation profile of the same length, in feet. Never return
grade — GradeIT computes that once, from the final elevation. The coordinates are passed in so you
can work in real distance along the ground rather than in point indices, which is almost always
what you want.
