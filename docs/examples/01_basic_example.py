"""
# Your First Grade Profile

This example uses a real GPS trace. It adds elevation and road grade data to
the trace.

The trace has 250 points along US-6, west of Golden, Colorado. This is about
7.7 miles of road through varying terrain. The GPS logged a point about once a second. The
elevation data comes from the USGS 1/3 arc-second Digital Elevation Model.

This example runs offline. The DEM tile is a small crop file, stored under
`docs/data/`. The original file is 411 MB. The crop file is much smaller, so
CI can build the documentation without a download. See
[Elevation Data](../elevation_data) for steps to use the real, full-size
tiles.
"""


def main():
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    from _data import TILE_DIR, load_coords
    from gradeit import USGSLocal, gradeit

    """
    ## Loading a trace

    `gradeit()` accepts many input types. It accepts a pandas `DataFrame`. It
    accepts a numpy `(n, 2)` array. It accepts a dict in the form
    `{"latitude": [...], "longitude": [...]}`. It also accepts any iterable of
    `(latitude, longitude)` pairs. This example uses the last form, so it does
    not need pandas yet.
    """

    trace = load_coords("golden_creek")

    print(f"{len(trace)} points")
    print(f"first: {trace[0]}")
    print(f"last:  {trace[-1]}")

    """
    ## Choosing an elevation model

    Elevation data comes from an `ElevationModel`. gradeit provides two
    built-in models:

    - `USGSApi()` — the online USGS Elevation Point Query Service. It needs no
      setup, but it sends one HTTP request *per point*. Use it for spot
      checks, not for whole traces. This is the default model if you pass
      none.
    - `USGSLocal(path)` — reads raster tiles stored on your local disk. It is
      much faster for a whole trace. You must first download the tiles to
      disk.

    This example uses `USGSLocal` and points it to the committed crop file.
    """

    elevation_model = USGSLocal(TILE_DIR)

    """
    ## Appending grade

    This call does the whole job. If you omit the `elevation_filter`
    argument, `gradeit()` applies `Wood2014Filter`. This is the filtration
    routine from Wood et al. (2014). Use this default filter in almost all
    cases.
    """

    result = gradeit(trace, elevation_model=elevation_model)

    """
    `gradeit()` returns a `GradeResult`, a frozen container of numpy arrays.
    `gradeit()` never modifies your input data.

    `GradeResult` keeps both the raw and the filtered profiles. `elevation_ft`
    and `grade_dec` hold the raw, unmodified DEM lookup. `elevation_ft_filtered`
    and `grade_dec_filtered` hold the cleaned values. **Use the filtered
    values.** The raw DEM profile has bridge artifacts and sampling noise.
    """

    print(f"elevation_ft           {result.elevation_ft[:4].round(1)} ...")
    print(f"elevation_ft_filtered  {result.elevation_ft_filtered[:4].round(1)} ...")
    print(f"grade_dec              {result.grade_dec[:4].round(4)} ...")
    print(f"grade_dec_filtered     {result.grade_dec_filtered[:4].round(4)} ...")
    print(f"distances_ft           {result.distances_ft[:4].round(1)} ...")

    """
    Grade is a decimal rise-over-run value. Multiply it by 100 to get a
    percent value. Distances are in feet. `distances_ft` starts with a
    leading `0.0` value, so each entry lines up with the same index in the
    other arrays. The per-segment distances are `distances_ft[1:]`.
    """

    total_mi = result.distances_ft.sum() / 5280
    climb_ft = result.elevation_ft_filtered.max() - result.elevation_ft_filtered.min()
    print(f"\ntrace length      {total_mi:.2f} miles")
    print(f"elevation range   {climb_ft:.0f} ft")
    print(f"steepest grade    {100 * np.abs(result.grade_dec_filtered).max():.2f}%")

    """
    ## Looking at it as a table

    `to_dataframe()` builds a table from the result, for inspection or
    export. This method needs pandas (`pip install gradeit[pandas]`). Use
    `to_dict()` instead if you do not have pandas; it gives you the same
    columns.

    Note one naming difference: the tabular output names the raw grade column
    `grade_dec_unfiltered`. The `GradeResult` attribute for the same data is
    named `grade_dec`.
    """

    df = result.to_dataframe()
    print(df.head())

    """
    ## Plotting the profile

    A plot of the raw profile against the filtered profile shows what the
    filter did. The two elevation curves sit almost on top of each other.
    This is expected: filtration removes artifacts, but it does not reshape
    the terrain. The grade panel tells a different story, because
    differentiation of a noisy signal amplifies the noise.
    """

    fig, (ax_elev, ax_grade) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    miles = np.cumsum(result.distances_ft) / 5280

    ax_elev.plot(miles, result.elevation_ft, lw=1, alpha=0.6, label="raw DEM")
    ax_elev.plot(miles, result.elevation_ft_filtered, lw=1.5, label="filtered")
    ax_elev.set_ylabel("elevation (ft)")
    ax_elev.legend()
    ax_elev.set_title("US-6 west of Golden, CO")

    ax_grade.plot(miles, 100 * result.grade_dec, lw=1, alpha=0.6, label="raw DEM")
    ax_grade.plot(miles, 100 * result.grade_dec_filtered, lw=1.5, label="filtered")
    ax_grade.axhline(0, color="k", lw=0.5)
    ax_grade.set_ylabel("grade (%)")
    ax_grade.set_xlabel("distance (miles)")
    ax_grade.legend()

    fig.tight_layout()
    plt.show()

    """
    The spike near mile 4.5 in the raw grade is not a hill. It marks a creek
    crossing. At this point, the bare-earth DEM reports the streambed
    elevation instead of the road deck elevation.
    [How Filtration Works](02_filtering_example) examines this artifact in
    detail.
    """

    print(f"\nraw      max |grade|  {100 * np.abs(result.grade_dec).max():6.2f}%")
    print(f"filtered max |grade|  {100 * np.abs(result.grade_dec_filtered).max():6.2f}%")

    assert isinstance(df, pd.DataFrame)


if __name__ == "__main__":
    main()
