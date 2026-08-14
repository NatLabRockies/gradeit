# Quickstart

The whole library is one function.

```python
from gradeit import gradeit

result = gradeit(trace)
```

Everything else is choosing where elevation comes from and how it gets cleaned.

## Input

`trace` can be any of these — GradeIT detects the form:

```python
import numpy as np
import pandas as pd

from gradeit import Coordinate, gradeit

gradeit(pd.DataFrame({"latitude": lats, "longitude": lons}))  # DataFrame
gradeit(np.array([[39.74, -105.0], [39.75, -105.0]]))  # (n, 2) array, (lat, lon) rows
gradeit({"latitude": lats, "longitude": lons})  # mapping
gradeit([(39.74, -105.0), (39.75, -105.0)])  # (lat, lon) pairs
gradeit([Coordinate.from_lat_lon(39.74, -105.0), ...])  # Coordinate objects
```

If your DataFrame uses different column names, say so:

```python
gradeit(df, lat_col="lat", lon_col="lon")
```

Points must be **in travel order** — grade is computed between consecutive points — and there
must be at least two of them. Your input is never modified.

## Output

`gradeit()` returns a `GradeResult`, a frozen container of numpy arrays:

```python
result.elevation_ft  # raw DEM lookup, feet
result.grade_dec  # grade from the raw lookup, decimal rise/run
result.elevation_ft_filtered  # cleaned elevation, feet
result.grade_dec_filtered  # grade recomputed from the cleaned elevation
result.distances_ft  # distance from the previous point, feet
result.coordinates  # the parsed input coordinates
```

**Use the `_filtered` arrays.** The raw profile is kept so you can audit what changed, but it
contains bare-earth artifacts and sampling noise that produce grade spikes no vehicle drove. The
`_filtered` fields are `None` if — and only if — you disabled filtering, which makes the
filtered-or-not contract explicit rather than silent.

Grade is a **decimal** rise over run, so multiply by 100 for percent. `distances_ft` carries a
leading `0.0` so it aligns point-for-point with the other arrays; the per-segment distances are
`distances_ft[1:]`.

To get a table:

```python
df = result.to_dataframe()  # needs gradeit[pandas]
d = result.to_dict()  # same columns, plain lists
```

```{note}
In the tabular output the raw grade column is named `grade_dec_unfiltered`, while the attribute
on `GradeResult` is `grade_dec`. The other names match.
```

## Choosing an elevation model

The default is `USGSApi()`, the online USGS Elevation Point Query Service. It needs no setup, but
it makes one HTTP request **per point** — fine for a spot check, far too slow for a trace.

For real traces, download the raster tiles once and use `USGSLocal`:

```python
from gradeit import USGSLocal, gradeit

result = gradeit(trace, elevation_model=USGSLocal("path/to/tiles"))
```

See [Elevation Data](elevation_data) for how to get the tiles, and
[Custom Elevation Sources](examples/05_custom_elevation_model_example) if your elevation comes
from somewhere else entirely.

## Choosing a filter

Passing nothing gives you `Wood2014Filter`, which is the right answer almost always:

```python
result = gradeit(trace, elevation_model=model)  # Wood2014Filter applied
```

To disable filtering, or to compose filters:

```python
from gradeit import BridgeFilter, Wood2014Filter

gradeit(trace, elevation_model=model, elevation_filter=None)  # raw only
gradeit(trace, elevation_model=model, elevation_filter=Wood2014Filter(savgol_window_ft=1200))
gradeit(
    trace,
    elevation_model=model,
    elevation_filter=[BridgeFilter(baseline_radius_ft=6000), Wood2014Filter()],
)
```

Sequences are applied in order, each consuming the previous filter's output, and grade is always
recomputed from the final elevation so the two never disagree. If you use `BridgeFilter`, put it
first — it keys on raw dip magnitude, which any smoother attenuates.

See [Filters](filters) for the full parameter reference and
[How Filtration Works](examples/02_filtering_example) for what turning the knobs actually does.

## Next

[Your First Grade Profile](examples/01_basic_example) runs all of this on a real trace.
