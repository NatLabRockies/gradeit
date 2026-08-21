# Plotting

GradeIT can draw a trace on an interactive [folium](https://python-visualization.github.io/folium/)
map. The color of each segment shows its grade. The map helps you find DEM artifacts. These appear
as sharp red notches where the bare-earth model drops below the road.

```bash
pip install gradeit[plot]
```

```python
from gradeit import gradeit, plot_grade_map

result = gradeit(trace, elevation_model=model)

m = result.plot_map()  # equivalent to plot_grade_map(result)
m.save("trace.html")
```

`plot_map()` is a `GradeResult` wrapper. Both functions return a `folium.Map`. A notebook can show
this map inline. See [Mapping a Trace](examples/04_plotting_example).

## Layers

If the result has raw and filtered profiles, the map draws two toggleable layers. Both layers are
visible when the map opens. The filtered layer is on top. Clear **Filtered grade** to see raw
artifacts. This shows where the filter changed the result.

Point to a segment to see its array index, grade, elevation, and length. You can then find the
matching row in your data.

## Options

```python
plot_grade_map(
    result,
    grade="auto",  # "auto" | "raw" | "filtered" | "both"
    grade_range_pct=None,  # (vmin, vmax) percent, or None to auto-scale
    weight=5,  # stroke width in pixels
    opacity=0.85,
    tiles="CartoDB positron",
    show_endpoints=True,
)
```

**`grade`** selects layers. `"auto"` draws both layers when filtering ran. Otherwise, it draws the
raw layer. `"filtered"` and `"both"` require a filter.

**`grade_range_pct`** sets the color scale. If it is `None`, GradeIT sets a symmetric range around
zero from the largest absolute grade. The midpoint color means flat. Set a range such as `(-8, 8)`
to compare maps or to prevent one artifact from changing the scale.

**`tiles`** sets the base map and passes the value to `folium.Map`. The default is
`"CartoDB positron"`. Its gray colors keep attention on grade. `"CartoDB Voyager"` shows more road
labels. `"CartoDB dark_matter"` uses a dark style.

```{note}
**Blank map or 403 base-map errors.** The
[OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/) blocks some heavy
or automated clients. A blocked client receives 403 errors. `"OpenStreetMap"` is not the default
for this reason. Use a CartoDB base map if the map is blank.
```

```{note}
**Untrusted notebooks.** An inline display can show "Make this notebook trusted to load map". The
VS Code Interactive Window has no trust setting. For `.ipynb` files, use **Notebook: Manage Trust**
in the Command Palette. You can also save `trace.html` and open it in a browser.
```

## A note on size

Each segment becomes a polyline with a tooltip. Generated HTML size increases with point count. A
trace with thousands of points creates a large file that opens slowly. For a long trace, plot a
slice, subsample, or pass `grade="filtered"`.
