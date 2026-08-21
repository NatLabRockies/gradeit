# Concepts

GradeIT terms and important conventions.

## Units

GradeIT names show units:

| Quantity  | Unit                            | Suffix |
| --------- | ------------------------------- | ------ |
| Elevation | feet                            | `_ft`  |
| Distance  | feet                            | `_ft`  |
| Grade     | decimal rise/run                | `_dec` |
| Latitude  | decimal degrees, north positive | —      |
| Longitude | decimal degrees, west negative  | —      |

Grade is a **decimal**, not a percentage: a 6% grade is `0.06`. Multiply by 100 to display.

Filter parameters use **feet**, never sample counts. GPS traces use time sampling. A fixed
point-count window has a different physical width at different vehicle speeds. Widths in feet keep
filter behavior consistent. See
[How Filtration Works](examples/02_filtering_example) for a measurement of how much that matters.

Elevation models, including custom models, return **feet**. GradeIT does not convert units.

## `Coordinate`

A frozen dataclass with `latitude` and `longitude`:

```python
from gradeit import Coordinate

point = Coordinate.from_lat_lon(39.7392, -105.0)
```

You rarely create these objects. `gradeit()` creates them from your input. They occur in
`GradeResult.coordinates` and `ElevationModel.get_elevation()`.

## Coordinate input

`gradeit()` accepts these forms in this order:

1. a numpy array of shape `(n, 2)` with `(latitude, longitude)` rows
2. anything with a `.columns` attribute — a pandas DataFrame, duck-typed
3. a mapping keyed by `lat_col` / `lon_col`
4. any other iterable of `Coordinate` or `(latitude, longitude)` pairs

`lat_col` and `lon_col` (default `"latitude"` / `"longitude"`) apply only to forms 2 and 3.
Anything else raises `InvalidInputError`.

Use **latitude first**. GradeIT uses `(lat, lon)`, not `(x, y)`.

## `GradeResult`

A frozen dataclass of numpy arrays. All arrays have the same length as the input.

```python
result.coordinates  # List[Coordinate]
result.elevation_ft_unfiltered  # np.ndarray, raw DEM lookup
result.distances_ft  # np.ndarray, distance from previous point
result.grade_dec_unfiltered  # np.ndarray, grade from the raw lookup
result.elevation_ft_filtered  # np.ndarray | None
result.grade_dec_filtered  # np.ndarray | None
```

Important conventions:

- **`distances_ft` carries a leading `0.0`** so it aligns point-for-point with the elevation and
  grade arrays. The per-segment distances are `distances_ft[1:]`, and `distances_ft.sum()` is the
  total trace length.

## `ElevationModel`

An abstract base class with one abstract method:

```python
class ElevationModel(metaclass=ABCMeta):
    @abstractmethod
    def get_elevation(self, trace: List[Coordinate]) -> List[float]: ...
```

Return elevation in **feet**. Return one value for each input coordinate in the **same order**. Use
**`NaN`** for a point without data. GradeIT includes `USGSApi` and `USGSLocal`. See
[Elevation Data](elevation_data) and [this example](examples/05_custom_elevation_model_example).

## `ElevationFilter`

Also one method:

```python
class ElevationFilter(metaclass=ABCMeta):
    @abstractmethod
    def filter(
        self, elevation_profile: List[float], coordinates: List[Coordinate]
    ) -> List[float]: ...
```

A filter takes an elevation profile and returns an elevation profile. It does **not** return grade.
You can pass a filter sequence. Each filter uses the output from the last filter. GradeIT calculates
grade from final elevation.

Built in: `Wood2014Filter` (the default) and `BridgeFilter`. See [Filters](filters).

## Exceptions

All GradeIT errors derive from `GradeitError`. Specific errors also subclass the matching built-in
error. Existing `except ValueError:` handlers keep working:

| Exception                | Also a        | Raised when                                     |
| ------------------------ | ------------- | ----------------------------------------------- |
| `GradeitError`           | `Exception`   | base class for everything below                 |
| `InvalidInputError`      | `ValueError`  | unsupported input form, fewer than 2 points     |
| `MissingDependencyError` | `ImportError` | an optional extra is needed but not installed   |
| `ElevationLookupError`   | —             | an elevation source returned something unusable |

A missing raster tile raises `FileNotFoundError`, not a GradeIT error. A point without elevation
data is `NaN`, not an exception.

Warnings derive from `GradeitWarning`. It is a `UserWarning`, not a `GradeitError`:

| Warning             | Raised when                                                           |
| ------------------- | --------------------------------------------------------------------- |
| `GradeitWarning`    | base class for everything below                                       |
| `SparseGridWarning` | `Wood2014Filter`'s `interval_ft` is finer than the GPS points support |

Escalate a category to an error with `warnings.simplefilter("error", GradeitWarning)`, or silence
it with `"ignore"`.
