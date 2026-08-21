# Quickstart

The main library function is `gradeit()`.

```python
from gradeit import gradeit

result = gradeit(trace)
```

## Input

A `trace` is a sequence of points and can have any of these forms. GradeIT detects the form:

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

Set the column names if your DataFrame uses different names:

```python
gradeit(df, lat_col="lat", lon_col="lon")
```

Points must be in **travel order**. GradeIT calculates grade between consecutive points. You must
provide at least two points. GradeIT does not change your input.

## Output

`gradeit()` returns a `GradeResult`. This frozen container has NumPy arrays:

```python
result.elevation_ft  # raw DEM lookup, feet
result.grade_dec  # grade from the raw lookup, decimal rise/run
result.elevation_ft_filtered  # cleaned elevation, feet
result.grade_dec_filtered  # grade recomputed from the cleaned elevation
result.distances_ft  # distance from the previous point, feet
result.coordinates  # the parsed input coordinates
```

**Use the `_filtered` arrays.** The raw profile stays available for comparison. It contains
bare-earth artifacts and sampling noise. These can create grade spikes.

Grade is a **decimal** rise over run. Multiply it by 100 to get a percentage. `distances_ft` starts
with `0.0`.

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

The default is `USGSApi()`, the online USGS Elevation Point Query Service. It needs no setup. It
makes one HTTP request for each point. Use it only for testing and not running large traces.

For a large trace, download raster tiles and use `USGSLocal`:

```python
from gradeit import USGSLocal, gradeit

result = gradeit(trace, elevation_model=USGSLocal("path/to/tiles"))
```

See [Elevation Data](elevation_data) to get the tiles. See
[Custom Elevation Sources](examples/05_custom_elevation_model_example) to use another data source.

## Choosing a filter

If you do not pass a filter, GradeIT uses `Wood2014Filter`. This is suitable for most traces:

```python
result = gradeit(trace, elevation_model=model)  # Wood2014Filter applied
```

To disable filtering or use more than one filter:

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

GradeIT applies filters in order. Each filter receives the output from the last filter. GradeIT
calculates grade from the final elevation. If you have large bridge artifacts, put `BridgeFilter` first.
See [Filters](filters) for all parameters. See
[How Filtration Works](examples/02_filtering_example) for filter behavior.

## Next

[Your First Grade Profile](examples/01_basic_example) runs all of this on a real trace.
