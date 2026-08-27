"""
# Mapping a Trace

If you want to inspect the results in a bit more detail, you can use the interactive map.

This feature needs the plotting extra:

```bash
pip install gradeit[plot]
```
"""


def main():
    import numpy as np
    from _data import TILE_DIR, load_coords

    from gradeit import USGSLocal, gradeit

    trace = load_coords("golden_creek")
    result = gradeit(trace, elevation_model=USGSLocal(TILE_DIR))

    print(f"raw max |grade|      {100 * np.abs(result.grade_dec_unfiltered).max():.1f}%")
    print(f"filtered max |grade| {100 * np.abs(result.grade_dec_filtered).max():.1f}%")

    """
    ## Drawing the map

    `result.plot_map()` is a thin wrapper around `gradeit.plot_grade_map()`.
    It returns a `folium.Map`, which renders inline in a notebook.

    This result has both a raw and a filtered profile. So the map draws them
    as two layers that you can toggle. Both layers are visible when the map
    loads, with the filtered layer on top. Use the layer control in the top
    right to untick **Filtered grade** and reveal the raw layer underneath.

    Hover over any segment to see its array index, grade, elevation, and
    length. This lets you jump straight from something suspicious on the map
    to the matching row in your data.
    """

    result.plot_map(grade_range_pct=(-8, 8))

    """
    ## Options worth knowing

    - **`grade_range_pct=(vmin, vmax)`** pins the color scale, as shown
      above. If you leave this at `None`, the scale spans the trace's own
      largest absolute grade, so the midpoint color always means flat. This
      is convenient, but it makes two maps hard to compare, and it lets one
      artifact wash out the rest.
    - **`grade=`** picks the layers to show: `"raw"`, `"filtered"`, `"both"`,
      or the default `"auto"` (shows both layers when filtering ran, or raw
      only otherwise).
    - **`tiles=`** changes the basemap. The default, `"CartoDB positron"`, is
      a muted grey basemap, chosen so the grade colors carry the signal.
      `"CartoDB Voyager"` adds road labels. `"CartoDB dark_matter"` is the
      dark equivalent.
    - **`weight=`** and **`opacity=`** control the stroke.
    - **`show_endpoints=False`** removes the start and end markers.

    To save a map instead of displaying it:

    ```python
    m = result.plot_map(grade_range_pct=(-8, 8))
    m.save("trace.html")
    ```
    """

    print(f"map built with {len(result.coordinates)} points")


if __name__ == "__main__":
    main()
