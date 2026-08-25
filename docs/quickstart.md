# Quickstart

The main library function is `gradeit()`.

The simplest way to use the package is to call `gradeit()` with a trace of points.
This uses all of the defaults and should work well out of the box.

```python
from gradeit import gradeit

trace = [
    (39.7392, -104.9903),
    (39.7402, -104.9903),
    (39.7412, -104.9903),
]
result = gradeit(trace)
```

## Input

A `trace` is a sequence of points and can have any of these forms. GradeIT detects the form:

```python
import numpy as np
import pandas as pd

from gradeit import Coordinate, gradeit

lats = [39.7392, 39.7402, 39.7412]
lons = [-104.9903, -104.9903, -104.9903]

gradeit(pd.DataFrame({"latitude": lats, "longitude": lons}))  # DataFrame
gradeit(np.column_stack((lats, lons)))  # (n, 2) array, (lat, lon) rows
gradeit({"latitude": lats, "longitude": lons})  # mapping
gradeit(list(zip(lats, lons)))  # (lat, lon) pairs
gradeit([Coordinate.from_lat_lon(lat, lon) for lat, lon in zip(lats, lons)])  # Coordinate objects
```

Set the column names if your DataFrame uses different names:

```python
import pandas as pd

from gradeit import gradeit

df = pd.DataFrame(
    {
        "lat": [39.7392, 39.7402, 39.7412],
        "lon": [-104.9903, -104.9903, -104.9903],
    }
)
gradeit(df, lat_col="lat", lon_col="lon")
```

Points must be in **travel order**. GradeIT calculates grade between consecutive points. You must
provide at least two points. GradeIT does not change your input.

## Output

`gradeit()` returns a `GradeResult`. This frozen container has NumPy arrays:

```python
from gradeit import gradeit

result = gradeit([(39.7392, -104.9903), (39.7402, -104.9903), (39.7412, -104.9903)])

result.elevation_ft_unfiltered  # raw DEM lookup, feet
result.grade_dec_unfiltered  # grade from the raw lookup, decimal rise/run
result.elevation_ft_filtered  # cleaned elevation, feet
result.grade_dec_filtered  # grade recomputed from the cleaned elevation
result.distances_ft  # distance from the previous point, feet
result.coordinates  # the parsed input coordinates
```

Grade is a **decimal** rise over run. Multiply it by 100 to get a percentage. `distances_ft` starts
with `0.0`.

To get a table:

```python
from gradeit import gradeit

result = gradeit([(39.7392, -104.9903), (39.7402, -104.9903), (39.7412, -104.9903)])

df = result.to_dataframe()  # needs gradeit[pandas]
d = result.to_dict()  # same columns, plain lists
```

## Choosing an elevation model

The default is `USGSApi()`, which pings the online USGS 3DEP service.
This works right out of the box but it requires API calls.
For better performance, download raster tiles and use `USGSLocal`:

```python
from gradeit import USGSLocal, gradeit

trace = [(39.7392, -104.9903), (39.7402, -104.9903), (39.7412, -104.9903)]
result = gradeit(trace, elevation_model=USGSLocal("path/to/tiles"))
```

See [Elevation Data](elevation_data) to get the tiles.

See [Custom Elevation Sources](examples/05_custom_elevation_model_example) to develop a model for a custom data source.

## Choosing a filter

If you do not pass a filter, GradeIT uses `Wood2014Filter`. This is suitable for most traces:

```python
from gradeit import gradeit

trace = [(39.7392, -104.9903), (39.7402, -104.9903), (39.7412, -104.9903)]
result = gradeit(trace)  # Wood2014Filter applied
```

To disable filtering or use more than one filter:

```python
from gradeit import BridgeFilter, Wood2014Filter, gradeit

trace = [(39.7392, -104.9903), (39.7402, -104.9903), (39.7412, -104.9903)]

gradeit(trace, elevation_filter=None)  # raw only
gradeit(trace, elevation_filter=Wood2014Filter(savgol_window_ft=1200))
gradeit(
    trace,
    elevation_filter=[BridgeFilter(baseline_radius_ft=6000), Wood2014Filter()],
)
```

GradeIT applies filters in order. Each filter receives the output from the last filter. GradeIT
calculates grade from the final elevation. If you have large bridge artifacts, put `BridgeFilter` first (see [Bare-Earth Bridges](examples/03_bridges_example)).
See [Filters](filters) for all parameters. See
[How Filtration Works](examples/02_filtering_example) for filter behavior.

## Next

[Your First Grade Profile](examples/01_basic_example) runs all of this on a real trace.
