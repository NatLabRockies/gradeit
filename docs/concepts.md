# Concepts

The vocabulary GradeIT uses, and the conventions that are easy to get wrong.

## Units

GradeIT is unit-explicit in its names and consistent about it:

| Quantity  | Unit                            | Suffix |
| --------- | ------------------------------- | ------ |
| Elevation | feet                            | `_ft`  |
| Distance  | feet                            | `_ft`  |
| Grade     | decimal rise/run                | `_dec` |
| Latitude  | decimal degrees, north positive | —      |
| Longitude | decimal degrees, west negative  | —      |

Grade is a **decimal**, not a percentage: a 6% grade is `0.06`. Multiply by 100 to display.

Filter parameters are declared in **feet**, never in sample counts — a design rule, not an
accident. GPS traces are sampled in time, so a fixed point-count window has a physical width that
changes with vehicle speed. Declaring widths in feet keeps a filter's behavior the same whether
the vehicle was crawling or at highway speed. See
[How Filtration Works](examples/02_filtering_example) for a measurement of how much that matters.

Elevation models return **feet** too, including custom ones. GradeIT does no unit conversion on
your behalf.

## `Coordinate`

A frozen dataclass holding `latitude` and `longitude`:

```python
from gradeit import Coordinate

point = Coordinate.from_lat_lon(39.7392, -105.0)
```

You rarely construct these — `gradeit()` builds them from whatever you pass. They show up on
`GradeResult.coordinates` and as the argument to `ElevationModel.get_elevation()`.

## Coordinate input

`gradeit()` accepts several forms, detected in this order:

1. a numpy array of shape `(n, 2)` with `(latitude, longitude)` rows
2. anything with a `.columns` attribute — a pandas DataFrame, duck-typed
3. a mapping keyed by `lat_col` / `lon_col`
4. any other iterable of `Coordinate` or `(latitude, longitude)` pairs

`lat_col` and `lon_col` (default `"latitude"` / `"longitude"`) apply only to forms 2 and 3.
Anything else raises `InvalidInputError`.

Note the ordering convention: **latitude first**, matching the `(lat, lon)` convention rather
than the `(x, y)` one.

## `GradeResult`

A frozen dataclass of numpy arrays. All arrays have the same length as the input.

```python
result.coordinates  # List[Coordinate]
result.elevation_ft  # np.ndarray, raw DEM lookup
result.distances_ft  # np.ndarray, distance from previous point
result.grade_dec  # np.ndarray, grade from the raw lookup
result.elevation_ft_filtered  # np.ndarray | None
result.grade_dec_filtered  # np.ndarray | None
```

Two conventions worth internalizing:

- **`distances_ft` carries a leading `0.0`** so it aligns point-for-point with the elevation and
  grade arrays. The per-segment distances are `distances_ft[1:]`, and `distances_ft.sum()` is the
  total trace length.
- **The `_filtered` fields are `None` exactly when filtering did not run.** They are not silently
  set equal to the raw arrays, so `result.grade_dec_filtered is None` is a reliable test for
  "I disabled filtering".

`to_dict()` and `to_dataframe()` materialize the result:

```{warning}
In the tabular output the raw grade column is named **`grade_dec_unfiltered`**, while the
attribute is `grade_dec`. This is for backward compatibility with older GradeIT output. Every
other column name matches its attribute.
```

`to_dataframe()` raises `MissingDependencyError` if pandas is not installed; `to_dict()` always
works.

## `ElevationModel`

An abstract base class with one abstract method:

```python
class ElevationModel(metaclass=ABCMeta):
    @abstractmethod
    def get_elevation(self, trace: List[Coordinate]) -> List[float]:
        ...
```

The contract: return elevation in **feet**, one value per input coordinate, in the **same order**,
using **`NaN`** for points you have no data for. Built in: `USGSApi` and `USGSLocal`
([Elevation Data](elevation_data)). Writing your own is
[a short example](examples/05_custom_elevation_model_example).

## `ElevationFilter`

Also one method:

```python
class ElevationFilter(metaclass=ABCMeta):
    @abstractmethod
    def filter(
        self, elevation_profile: List[float], coordinates: List[Coordinate]
    ) -> List[float]:
        ...
```

A filter takes an elevation profile and returns an elevation profile — **never grade**. That
symmetry is what makes filters composable: pass a sequence and each one consumes the previous
one's output. Grade is computed once, at the end, from the final elevation, so elevation and
grade can never disagree.

Filters receive the coordinates as well as the elevations because most of them need real
distances along the ground, not point indices.

Built in: `Wood2014Filter` (the default), `BridgeFilter`, and `SavitzkyGolayFilter`. See
[Filters](filters).

## Exceptions

All GradeIT errors derive from `GradeitError`, and the specific ones also subclass the matching
builtin so existing `except ValueError:` handlers keep working:

| Exception                | Also a        | Raised when                                     |
| ------------------------ | ------------- | ----------------------------------------------- |
| `GradeitError`           | `Exception`   | base class for everything below                 |
| `InvalidInputError`      | `ValueError`  | unsupported input form, fewer than 2 points     |
| `MissingDependencyError` | `ImportError` | an optional extra is needed but not installed   |
| `ElevationLookupError`   | —             | an elevation source returned something unusable |

Note that a missing raster tile raises `FileNotFoundError` rather than a GradeIT error, and that
points with no elevation data are `NaN` rather than an exception.
