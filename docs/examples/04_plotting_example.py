"""
# Mapping a Trace

Numbers tell you *that* a filter intervened; a map tells you **where**. gradeit
ships an interactive folium map that draws each segment of the trace colored by
its grade, which makes bare-earth artifacts obvious at a glance — they show up as
sharp red notches on the raw layer where the DEM dips into whatever the road is
crossing.

This needs the plotting extra:

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

    print(f"raw max |grade|      {100 * np.abs(result.grade_dec).max():.1f}%")
    print(f"filtered max |grade| {100 * np.abs(result.grade_dec_filtered).max():.1f}%")

    """
    ## Drawing the map

    `result.plot_map()` is a thin wrapper around `gradeit.plot_grade_map()`. It
    returns a `folium.Map`, which renders inline in a notebook.

    Because this result has both a raw and a filtered profile, the map draws them
    as two toggleable layers, both visible at load with filtered on top. Use the
    layer control in the top right to untick **Filtered grade** and reveal the raw
    layer underneath — around the creek crossing the raw layer dives deep red
    while the filtered layer runs level.

    Hovering any segment shows its array index, grade, elevation, and length, so
    you can jump straight from something suspicious on the map to the
    corresponding row in your data.

    The trace's own 30% raw spike would otherwise stretch the color scale until
    every ordinary road grade washed out, so we pin the scale to +/-8%.
    """

    m = result.plot_map(grade_range_pct=(-8, 8))
    m

    """
    ## Options worth knowing

    - **`grade_range_pct=(vmin, vmax)`** pins the color scale, as above. Left at
      `None` the scale spans the trace's own largest absolute grade, so the
      midpoint color always means flat — convenient, but it makes two maps
      incomparable and lets one artifact wash out the rest.
    - **`grade=`** picks the layers: `"raw"`, `"filtered"`, `"both"`, or the
      default `"auto"` (both when filtering ran, raw otherwise).
    - **`tiles=`** changes the basemap. The default `"CartoDB positron"` is a
      muted grey chosen so the grade colors carry the signal. `"CartoDB Voyager"`
      adds road labeling; `"CartoDB dark_matter"` is the dark equivalent.
    - **`weight=`** and **`opacity=`** control the stroke.
    - **`show_endpoints=False`** drops the start/end markers.

    To save a map instead of displaying it:

    ```python
    m.save("trace.html")
    ```

    ```{note}
    openstreetmap.org's [tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
    blocks heavy or automated clients, and a blocked client gets 403s instead of
    tiles. That is why `OpenStreetMap` is not the default here. If you switch to
    it and the map comes up blank, that is the cause — switch back to a CartoDB
    basemap.
    ```

    ```{note}
    In the VS Code Interactive Window, inline display can show "Make this notebook
    trusted to load map". The Interactive Window has no trust toggle; `.ipynb`
    files do, via Command Palette → "Notebook: Manage Trust". The simplest
    workaround is to `m.save(...)` and open the HTML in a browser.
    ```
    """

    print(f"map built with {len(result.coordinates)} points")


if __name__ == "__main__":
    main()
