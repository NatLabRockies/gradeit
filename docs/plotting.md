# Plotting

GradeIT can draw a trace on an interactive [folium](https://python-visualization.github.io/folium/)
map with each segment colored by its grade. It is the fastest way to find DEM artifacts, which
show up as sharp red notches where the bare-earth model dips into whatever the road is crossing.

```bash
pip install gradeit[plot]
```

```python
from gradeit import gradeit, plot_grade_map

result = gradeit(trace, elevation_model=model)

m = result.plot_map()  # equivalent to plot_grade_map(result)
m.save("trace.html")
```

`plot_map()` is a convenience wrapper on `GradeResult`; both return a `folium.Map`, which renders
inline in a notebook. See [Mapping a Trace](examples/04_plotting_example) for a live one.

## Layers

When the result has both a raw and a filtered profile, the map draws them as two toggleable
layers — both visible at load, filtered on top. Untick **Filtered grade** in the layer control to
see the raw artifacts underneath. That side-by-side is the point: it shows exactly where the
filter intervened and lets you judge whether it should have.

Hovering a segment reveals its array index, grade, elevation, and length, so you can go straight
from something suspicious on the map to the corresponding row in your data.

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

**`grade`** picks the layers. `"auto"` draws both when filtering ran and raw otherwise;
`"filtered"` and `"both"` require that `gradeit()` was called with a filter.

**`grade_range_pct`** pins the color scale. Left as `None`, the range is set symmetrically around
zero from the trace's largest absolute grade, so the midpoint color always means flat. That is
convenient but it makes two maps incomparable, and a single artifact can stretch the scale until
all the real terrain washes to one color — pin it to something like `(-8, 8)` when that happens.

**`tiles`** sets the basemap, passed through to `folium.Map`. The default `"CartoDB positron"` is
a muted grey, chosen so the grade colors carry the signal rather than competing with OpenStreetMap's
own greens and yellows. `"CartoDB Voyager"` adds more road labeling; `"CartoDB dark_matter"` is
the dark equivalent.

```{note}
**Blank map or 403 errors on the basemap.** openstreetmap.org's
[tile usage policy](https://operations.osmfoundation.org/policies/tiles/) blocks heavy or
automated clients, and a blocked client receives 403s instead of tiles. That is why
`"OpenStreetMap"` is not the default. If you switch to it and the map comes up blank, that is the
cause — switch back to one of the CartoDB basemaps.
```

```{note}
**Untrusted notebooks.** Inline display can show "Make this notebook trusted to load map". The VS
Code Interactive Window has no trust toggle; `.ipynb` files do, via Command Palette → "Notebook:
Manage Trust". The simplest workaround either way is `m.save("trace.html")` and open it in a
browser.
```

## A note on size

Each segment becomes its own polyline with its own tooltip, so the generated HTML grows with the
point count — a few hundred points is well under a megabyte, but a multi-thousand-point trace
produces a large file that is slow to open. For long traces, plot a slice, subsample, or pass
`grade="filtered"` to halve the geometry.
