"""
# Your First Grade Profile

This example takes a real GPS trace and appends elevation and road grade to it.

The trace is 250 points along US-6 west of Golden, Colorado — about 7.7 miles of
canyon road, sampled roughly once a second. The elevation comes from the USGS
1/3 arc-second Digital Elevation Model.

Everything here runs offline. The DEM tile is a small crop committed under
`docs/data/`, cut down from the 411 MB original so the documentation can build on
CI without downloading anything. See [Elevation Data](../elevation_data) for how
to point gradeit at the real full-size tiles.
"""


def main():
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    from _data import TILE_DIR, load_coords
    from gradeit import USGSLocal, gradeit

    """
    ## Loading a trace

    `gradeit()` is flexible about input. It accepts a pandas `DataFrame`, a numpy
    `(n, 2)` array, a dict of `{"latitude": [...], "longitude": [...]}`, or any
    iterable of `(latitude, longitude)` pairs. Here we use the last form, so
    nothing depends on pandas yet.
    """

    trace = load_coords("golden_creek")

    print(f"{len(trace)} points")
    print(f"first: {trace[0]}")
    print(f"last:  {trace[-1]}")

    """
    ## Choosing an elevation model

    Elevation comes from an `ElevationModel`. There are two built in:

    - `USGSApi()` — the online USGS Elevation Point Query Service. No setup, but
      it issues one HTTP request *per point*, so it suits spot checks rather than
      whole traces. This is the default if you pass nothing.
    - `USGSLocal(path)` — reads locally downloaded raster tiles. Much faster for
      a whole trace, at the cost of having the tiles on disk.

    We use `USGSLocal` pointed at the committed crop.
    """

    elevation_model = USGSLocal(TILE_DIR)

    """
    ## Appending grade

    That is the whole call. With no `elevation_filter` argument, `gradeit()`
    applies `Wood2014Filter` — the filtration routine from Wood et al. (2014) —
    which is what you want almost always.
    """

    result = gradeit(trace, elevation_model=elevation_model)

    """
    The return value is a `GradeResult`: a frozen container of numpy arrays. Your
    input is never modified.

    Note that both the raw and the filtered profiles are kept. `elevation_ft` and
    `grade_dec` are the untouched DEM lookup; `elevation_ft_filtered` and
    `grade_dec_filtered` are the cleaned versions. **Use the filtered ones** —
    the raw DEM profile contains bridge artifacts and sampling noise that produce
    grade spikes no vehicle ever drove.
    """

    print(f"elevation_ft           {result.elevation_ft[:4].round(1)} ...")
    print(f"elevation_ft_filtered  {result.elevation_ft_filtered[:4].round(1)} ...")
    print(f"grade_dec              {result.grade_dec[:4].round(4)} ...")
    print(f"grade_dec_filtered     {result.grade_dec_filtered[:4].round(4)} ...")
    print(f"distances_ft           {result.distances_ft[:4].round(1)} ...")

    """
    Grade is a decimal rise-over-run, so multiply by 100 for percent. Distances
    are in feet, and `distances_ft` carries a leading `0.0` so it lines up
    point-for-point with the other arrays — the per-segment distances are
    `distances_ft[1:]`.
    """

    total_mi = result.distances_ft.sum() / 5280
    climb_ft = result.elevation_ft_filtered.max() - result.elevation_ft_filtered.min()
    print(f"\ntrace length      {total_mi:.2f} miles")
    print(f"elevation range   {climb_ft:.0f} ft")
    print(f"steepest grade    {100 * np.abs(result.grade_dec_filtered).max():.2f}%")

    """
    ## Looking at it as a table

    `to_dataframe()` materializes the result for inspection or export. It needs
    pandas (`pip install gradeit[pandas]`); `to_dict()` gives you the same
    columns without it.

    One naming quirk worth knowing: the raw grade column is called
    `grade_dec_unfiltered` in the tabular output, even though the attribute on
    `GradeResult` is `grade_dec`.
    """

    df = result.to_dataframe()
    print(df.head())

    """
    ## Plotting the profile

    Plotting raw against filtered shows what the filter actually did. The two
    elevation curves sit almost on top of each other — filtration is meant to
    remove artifacts, not to reshape terrain — but the grade panel tells a
    different story, because differentiating a noisy signal amplifies the noise.
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
    The spike near mile 3.5 in the raw grade is not a hill. It is a creek
    crossing where the bare-earth DEM reports the streambed instead of the road
    deck. [How Filtration Works](02_filtering_example) takes that artifact apart.
    """

    print(f"\nraw      max |grade|  {100 * np.abs(result.grade_dec).max():6.2f}%")
    print(f"filtered max |grade|  {100 * np.abs(result.grade_dec_filtered).max():6.2f}%")

    assert isinstance(df, pd.DataFrame)


if __name__ == "__main__":
    main()
