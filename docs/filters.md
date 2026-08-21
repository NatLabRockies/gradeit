# Filters

Raw DEM elevation profiles can have outliers and incorrect terrain. Causes include GPS position
noise, DEM resolution, and bare-earth artifacts below road structures. GradeIT uses one or more
`ElevationFilter` objects before it calculates grade.

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

GradeIT applies filter sequences in order. Each filter uses the output from the last filter.
GradeIT calculates grade from final elevation. All parameters use **feet**.

## `Wood2014Filter` — the default

This filter does steps B–E of [the Wood et al. method](methodology). It resamples to a uniform
distance grid, smooths, removes and fills unusual nodes, smooths again, and interpolates.

This is the default filter. It is suitable for most traces. It also removes ordinary bridge and
overpass artifacts without bridge-specific logic.

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
| `min_node_occupancy`    | `0.35`   | Guard on `interval_ft`: warn when fewer than this fraction of grid nodes contain a GPS point. Set to `0.0` to silence.             |

This frozen dataclass has a constructor argument for each parameter. You can share an instance.

### Tuning notes

**`savgol_window_ft`** controls smoothness. A wider value reduces grade noise. It also reduces real
short features. A wide bare-earth artifact can pull the smoothed road toward the artifact.

**`residual_threshold_ft`** defines an artifact. A lower value removes more data. A value about
twice the default can miss real artifacts. [This example](examples/02_filtering_example) shows a
creek crossing that remains at 16 ft.

**`residual_grow_ratio`** helps with wide artifacts. A wide artifact pulls the smoothed curve down.
This reduces the residual in the center. Without hysteresis, a per-node test removes only the
edges.

`resolve_parameters()` reports how feet values resolve to samples for a trace. It does not run the
filter:

```python
from gradeit.filters.wood2014 import resolve_parameters

delta_ft, window, polyorder, binomial_order = resolve_parameters(Wood2014Filter(), total_ft)
```

## `BridgeFilter` — targeted bare-earth correction

This filter finds dips below the nearby road on **both** sides. It interpolates road elevation
across each dip. This replaces a bridge that the DEM does not show.

The filter compares each point with a baseline from a rolling **maximum** elevation on each side.
It uses the lower side maximum. During a steady climb or descent, the baseline is the point
elevation. Uniform grade does not create a false positive.

The filter uses nearby high ground, not a smoothed signal. Therefore, it can find spans that the
`Wood2014Filter` residual test cannot find.

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
**A real valley can also sit below the road on both sides.** Geometry does not distinguish a valley
from a bridge. The checks above cannot always separate them.

`baseline_radius_ft` defines the difference. The one-mile default is suitable only for gentle
terrain. Use hundreds of feet for typical overpasses and creek crossings. Use thousands of feet
for a major water crossing. A value that is too wide can interpolate a straight line across a real
valley.
```

These examples show both errors:

- [How Filtration Works](examples/02_filtering_example) — the one-mile default flattening 1.5
  miles of real Colorado canyon by up to 130 ft, on a trace the default `Wood2014Filter` handles
  perfectly.
- [Bare-Earth Bridges](examples/03_bridges_example) — a 5,332 ft crossing of the Carquinez Strait
  that `Wood2014Filter` cannot touch at any setting, cleared once `baseline_radius_ft` covers the
  span.

**Order matters.** Put `BridgeFilter` first. A smoother reduces raw dip magnitude.

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

Take an elevation profile. Return an elevation profile of the same length in feet. Do not return
grade. GradeIT calculates grade from final elevation. The filter receives coordinates so it can use
real ground distance instead of point indexes.
