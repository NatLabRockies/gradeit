"""
# How Filtration Works

`gradeit()` filters the elevation profile before it computes grade. By
default, `gradeit()` uses `Wood2014Filter`. This is the five-step routine
from Wood et al. (2014), NREL/TP-5400-61109.

This page explains the steps. It shows why the parameters use *feet* instead
of sample counts. It also shows what happens when you change these
parameters. It uses the same Golden, Colorado trace as
[Your First Grade Profile](01_basic_example).

See [Methodology](../methodology) for the paper's five steps. See
[Filters](../filters) for the full parameter reference.
"""


def main():
    import matplotlib.pyplot as plt
    import numpy as np

    from _data import TILE_DIR, load_coords
    from gradeit import BridgeFilter, USGSLocal, Wood2014Filter, gradeit
    from gradeit.filters.wood2014 import resolve_parameters

    trace = load_coords("golden_creek")
    elevation_model = USGSLocal(TILE_DIR)

    """
    ## Start with no filter at all

    Pass `elevation_filter=None` to get the raw DEM lookup. Use this as the
    honest baseline for comparison.
    """

    raw = gradeit(trace, elevation_model=elevation_model, elevation_filter=None)

    print(f"filtered arrays populated? {raw.elevation_ft_filtered is not None}")
    print(f"raw max |grade|  {100 * np.abs(raw.grade_dec).max():.2f}%")

    """
    ## Why the parameters are in feet

    A GPS trace is sampled in **time**. So its spacing in **distance**
    changes with vehicle speed. On this trace:
    """

    spacing = raw.distances_ft[1:]
    print(f"point spacing (ft):  median {np.median(spacing):.0f}")
    print(f"                     p5     {np.percentile(spacing, 5):.0f}")
    print(f"                     p95    {np.percentile(spacing, 95):.0f}")
    print(f"                     range  {spacing.min():.0f} to {spacing.max():.0f}")

    """
    This is a sevenfold change between the 5th and 95th percentile. A filter
    with a fixed *point-count* window would have a physical cutoff that
    varies sevenfold along a single trace. It would smooth hard where the
    vehicle moved slowly, and barely at all where the vehicle moved fast.

    Step B of the routine resamples the trace onto a uniform distance grid
    first. This step makes a fixed cutoff in feet possible.
    `resolve_parameters()` shows what the declared feet resolve to on this
    trace, without running the filter:
    """

    total_ft = raw.distances_ft.sum()
    delta_ft, savgol_window, polyorder, binomial_order = resolve_parameters(
        Wood2014Filter(), total_ft
    )
    print(f"trace length           {total_ft:,.0f} ft")
    print(f"grid spacing           {delta_ft:.2f} ft  (from interval_ft=100)")
    print(f"Savitzky-Golay window  {savgol_window} nodes  (from savgol_window_ft=600)")
    print(f"polynomial order       {polyorder}")
    print(f"binomial order         {binomial_order}  (from binomial_sigma_ft=100)")

    """
    A 600 ft window becomes a 7-node kernel here. If you change
    `interval_ft`, the node count changes to keep the same 600 ft of road
    under the kernel.

    ## What the default actually changed

    The creek crossing sits at index 119 of this trace. The bare-earth DEM
    has no bridge deck in it. So the lookup drops into the streambed, and
    differentiation of that value produces a grade spike that no vehicle
    drove.
    """

    filtered = gradeit(trace, elevation_model=elevation_model)
    creek = 119

    lo, hi = creek - 3, creek + 4
    assert np.argmax(np.abs(filtered.elevation_ft_filtered - raw.elevation_ft)) == creek

    print("        raw DEM            default filter")
    print(" idx    elev_ft  grade     elev_ft  grade")
    for i in range(lo, hi):
        mark = "  <-- creek" if i == creek else ""
        print(
            f" {i:4d} {raw.elevation_ft[i]:9.1f} {100 * raw.grade_dec[i]:6.1f}%"
            f"  {filtered.elevation_ft_filtered[i]:9.1f} "
            f"{100 * filtered.grade_dec_filtered[i]:6.1f}%{mark}"
        )

    deck = (raw.elevation_ft[creek - 1] + raw.elevation_ft[creek + 1]) / 2
    print(f"\nroad deck implied by the clean neighbors: {deck:.1f} ft")
    print(f"  raw      {raw.elevation_ft[creek]:.1f} ft ({raw.elevation_ft[creek] - deck:+.1f})")
    print(
        f"  filtered {filtered.elevation_ft_filtered[creek]:.1f} ft "
        f"({filtered.elevation_ft_filtered[creek] - deck:+.1f})"
    )

    """
    Nothing above is bridge-specific. Step D discards nodes whose
    *filtration residual* is too large to be DEM noise. It then backfills
    these nodes by interpolation. A bare-earth artifact always has a large
    residual. So the default filter catches it, without ever being told that
    bridges exist.

    ## Filtration should not reshape terrain

    The paper states that filtration should not have a transformational
    effect on the underlying elevation layer. This claim is easy to check:
    the grade tail should collapse, while the elevation profile barely
    moves.
    """

    raw_pct = np.abs(100 * raw.grade_dec)
    filt_pct = np.abs(100 * filtered.grade_dec_filtered)
    print(f"{'':10}{'max':>8}{'p99':>8}{'p95':>8}")
    for label, g in (("raw", raw_pct), ("filtered", filt_pct)):
        print(f"{label:10}{g.max():7.2f}%{np.percentile(g, 99):7.2f}%{np.percentile(g, 95):7.2f}%")
    moved = np.abs(filtered.elevation_ft_filtered - raw.elevation_ft)
    print(f"\nmedian |filtered - raw| elevation: {np.median(moved):.2f} ft")
    print(f"max    |filtered - raw| elevation: {moved.max():.2f} ft  (at the creek)")

    """
    ## Turning the knobs

    `Wood2014Filter` is a frozen dataclass. Every parameter is a constructor
    argument. A wider `savgol_window_ft` value gives a smoother grade signal,
    but it also attenuates short, real features:
    """

    print("savgol_window_ft   max|grade|   p99   median |filtered-raw|")
    for window_ft in (300, 600, 1200, 2400):
        swept = gradeit(
            trace,
            elevation_model=elevation_model,
            elevation_filter=Wood2014Filter(savgol_window_ft=window_ft),
        )
        g = 100 * np.abs(swept.grade_dec_filtered)
        drift = np.median(np.abs(swept.elevation_ft_filtered - raw.elevation_ft))
        print(f"{window_ft:12d} ft {g.max():9.2f}% {np.percentile(g, 99):6.2f}% {drift:14.2f} ft")

    """
    `residual_threshold_ft` is the more interesting parameter: it decides
    what counts as an artifact. Its 8 ft default value is the DEM's own
    2.44 m vertical RMSE. A residual bigger than the elevation model's
    1-sigma accuracy cannot be explained as noise. If you raise the
    threshold too far, the filter stops rejecting the creek:
    """

    print("residual_threshold_ft   creek elev_ft   max|grade|")
    for threshold in (4, 8, 16, 32):
        swept = gradeit(
            trace,
            elevation_model=elevation_model,
            elevation_filter=Wood2014Filter(residual_threshold_ft=threshold),
        )
        print(
            f"{threshold:17d} ft {swept.elevation_ft_filtered[creek]:14.1f} "
            f"{100 * np.abs(swept.grade_dec_filtered).max():11.2f}%"
        )

    """
    At 16 ft and above, the creek survives filtration and the grade spike
    returns. The default values are not arbitrary.

    ## A filter that is wrong for this trace

    `BridgeFilter` targets bare-earth spans directly. It finds dips that sit
    below the surrounding road on both sides. This description also matches
    a real valley. Geometry alone cannot tell the two apart. The
    `baseline_radius_ft` parameter separates them; its default value is one
    mile.

    This trace runs through real canyon terrain. So the default radius is
    much too wide, and the filter interpolates straight across a genuine
    valley:
    """

    over = gradeit(trace, elevation_model=elevation_model, elevation_filter=BridgeFilter())
    delta = np.abs(over.elevation_ft_filtered - raw.elevation_ft)
    touched = np.flatnonzero(delta > 1.0)
    span_ft = raw.distances_ft[touched.min() : touched.max() + 1].sum()

    print(f"stock BridgeFilter moved {touched.size} of {len(trace)} points")
    print(f"  across {span_ft:,.0f} ft ({span_ft / 5280:.2f} miles) of road")
    print(f"  by up to {delta.max():.1f} ft")
    print(
        f"default Wood2014Filter moved {int((moved > 1.0).sum())} points, max {moved.max():.1f} ft"
    )

    """
    This is real terrain, erased quietly. The lesson is not that
    `BridgeFilter` is broken. [Bare-Earth Bridges](03_bridges_example) shows
    a trace where `BridgeFilter` is the only filter that works. The lesson
    is that you must scale the radius to the spans you want to correct. You
    should also always compare filtered output against raw output, across
    the *whole* trace, before you trust a filter.
    """

    fig, ax = plt.subplots(figsize=(10, 5))
    miles = np.cumsum(raw.distances_ft) / 5280
    ax.plot(miles, raw.elevation_ft, lw=1, alpha=0.5, color="0.4", label="raw DEM")
    ax.plot(miles, filtered.elevation_ft_filtered, lw=1.6, label="Wood2014Filter (default)")
    ax.plot(
        miles, over.elevation_ft_filtered, lw=1.4, ls="--", label="BridgeFilter() 1-mile default"
    )
    ax.set_xlabel("distance (miles)")
    ax.set_ylabel("elevation (ft)")
    ax.set_title("A filter tuned for the wrong scale flattens real terrain")
    ax.legend()
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
