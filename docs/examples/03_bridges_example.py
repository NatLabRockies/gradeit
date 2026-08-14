"""
# Bare-Earth Bridges

The USGS Digital Elevation Model is a **bare-earth** model: it describes the
ground, not the road. Where a road crosses a valley or a body of water on a
bridge, the DEM returns whatever is underneath — the streambed, the water
surface — and differentiating that produces grade spikes no vehicle ever drove.

This page uses 420 points of I-80 running north up the east side of San
Francisco Bay. The segment crosses **two** bare-earth artifacts that sit on
opposite sides of the default filter's competence, which makes it a good place
to see exactly where one tool ends and another begins.

Everything runs offline against the committed DEM crop in `docs/data/`.
"""


def main():
    import matplotlib.pyplot as plt
    import numpy as np

    from _data import TILE_DIR, load_coords
    from gradeit import BridgeFilter, USGSLocal, Wood2014Filter, gradeit

    trace = load_coords("carquinez")
    elevation_model = USGSLocal(TILE_DIR)

    # The two artifacts, as (first, last) index of the bad run.
    ARTIFACTS = {
        "short crossing": (33, 39),
        "Carquinez Strait": (232, 296),
    }

    """
    ## Characterizing the artifacts

    First, the raw profile with no filter, so we can measure what is actually
    wrong. For each artifact we compare the DEM floor against the road deck
    implied by the clean points on either side.
    """

    raw = gradeit(trace, elevation_model=elevation_model, elevation_filter=None)

    def deck_ft(first, last):
        """Elevation the road deck should have, from the clean neighbors."""
        return (raw.elevation_ft[first - 1] + raw.elevation_ft[last + 1]) / 2

    print(f"{'artifact':18}{'span_ft':>9}{'deck_ft':>9}{'DEM floor':>11}{'depth_ft':>10}")
    for label, (first, last) in ARTIFACTS.items():
        span = raw.distances_ft[first : last + 2].sum()
        deck = deck_ft(first, last)
        floor = raw.elevation_ft[first : last + 1].min()
        print(f"{label:18}{span:9,.0f}{deck:9.1f}{floor:11.1f}{deck - floor:10.1f}")

    print(f"\nraw max |grade| over the segment: {100 * np.abs(raw.grade_dec).max():.1f}%")

    """
    A 164 ft drop into open water, recovered over a few hundred feet of road, is
    what produces that 89% grade. No vehicle climbed an 89% grade on I-80.

    ## What the default filter does

    `Wood2014Filter` detects artifacts by **filtration residual**: it smooths the
    profile and flags points that sit far from their own smoothed version.
    """

    default = gradeit(trace, elevation_model=elevation_model)

    def residual_ft(result, first, last):
        """How far the filtered profile still sits below the implied deck."""
        elevation = result.elevation_ft_filtered
        if elevation is None:
            elevation = result.elevation_ft
        return abs(elevation[first : last + 1].min() - deck_ft(first, last))

    print(f"{'artifact':18}{'raw err':>10}{'after default':>15}")
    for label, (first, last) in ARTIFACTS.items():
        before = deck_ft(first, last) - raw.elevation_ft[first : last + 1].min()
        print(f"{label:18}{before:9.1f} {residual_ft(default, first, last):14.1f}")

    """
    The short crossing is gone. The Carquinez crossing is essentially untouched.

    That is not a tuning failure, it is structural. A residual detector is blind
    to any feature wider than its own smoothing kernel: the smoother simply
    follows a wide feature down, and the residual collapses to nothing. The
    strait is 5,332 ft across — far wider than any sensible kernel.

    ## Widening the window does not help

    If the problem were tuning, a wider `savgol_window_ft` would fix it. Sweeping
    it shows the opposite — the short crossing gets *worse* while the strait
    stays broken.
    """

    print(f"{'savgol_window_ft':>17}{'short':>9}{'Carquinez':>12}{'min elev_ft':>13}")
    for window_ft in (600, 1200, 2400, 4800, 9600):
        swept = gradeit(
            trace,
            elevation_model=elevation_model,
            elevation_filter=Wood2014Filter(savgol_window_ft=window_ft),
        )
        errors = [residual_ft(swept, *ARTIFACTS[k]) for k in ARTIFACTS]
        print(
            f"{window_ft:17,}{errors[0]:9.1f}{errors[1]:12.1f}"
            f"{swept.elevation_ft_filtered.min():13.1f}"
        )

    """
    Watch the last column. As the window widens the filter does not lift the deck
    out of the water — it drags the surrounding road *down toward* it, until the
    profile reports elevations below sea level. Smoothing harder is the wrong
    tool for this artifact.

    ## The filter that can reach it

    `BridgeFilter` compares each point against a two-sided **rolling-maximum
    baseline** — an absolute comparison against surrounding high ground rather
    than against a smoothed version of the signal. That reaches spans the
    residual method structurally cannot, provided its `baseline_radius_ft`
    window is wide enough to see real road beyond both ends of the span.
    """

    print(f"{'baseline_radius_ft':>19}{'Carquinez err':>15}{'max |grade|':>13}")
    for radius_ft in (2640, 4000, 5280, 6000, 9000):
        swept = gradeit(
            trace,
            elevation_model=elevation_model,
            elevation_filter=[BridgeFilter(baseline_radius_ft=radius_ft), Wood2014Filter()],
        )
        print(
            f"{radius_ft:19,}{residual_ft(swept, *ARTIFACTS['Carquinez Strait']):15.1f}"
            f"{100 * np.abs(swept.grade_dec_filtered).max():12.1f}%"
        )

    """
    There is a clean threshold: once the radius clears the 5,332 ft span, the
    correction lands. Below it, the baseline window never escapes the artifact
    and the filter correctly declines to act.

    ## The recommended pipeline

    Filters compose. Pass a sequence and each consumes the previous one's output.
    `BridgeFilter` goes **first** — it keys on raw dip magnitude, which any
    smoother attenuates.
    """

    combined = gradeit(
        trace,
        elevation_model=elevation_model,
        elevation_filter=[BridgeFilter(baseline_radius_ft=6000.0), Wood2014Filter()],
    )

    print(f"{'artifact':18}{'raw':>9}{'default':>10}{'combined':>10}")
    for label, (first, last) in ARTIFACTS.items():
        before = deck_ft(first, last) - raw.elevation_ft[first : last + 1].min()
        print(
            f"{label:18}{before:9.1f}{residual_ft(default, first, last):10.1f}"
            f"{residual_ft(combined, first, last):10.1f}"
        )
    print(
        f"\nmax |grade|  raw {100 * np.abs(raw.grade_dec).max():5.1f}%"
        f"   default {100 * np.abs(default.grade_dec_filtered).max():5.1f}%"
        f"   combined {100 * np.abs(combined.grade_dec_filtered).max():5.1f}%"
    )

    """
    ## Seeing it

    Both artifacts, three profiles. The strait is the wide one on the right.
    """

    fig, (ax_elev, ax_grade) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    miles = np.cumsum(raw.distances_ft) / 5280

    for ax, key, ylabel in (
        (ax_elev, "elev", "elevation (ft)"),
        (ax_grade, "grade", "grade (%)"),
    ):
        series = (
            ("raw DEM", raw.elevation_ft, raw.grade_dec, "0.45", 1.0, "-"),
            ("default", default.elevation_ft_filtered, default.grade_dec_filtered, "C0", 1.5, "-"),
            (
                "BridgeFilter + default",
                combined.elevation_ft_filtered,
                combined.grade_dec_filtered,
                "C1",
                1.5,
                "-",
            ),
        )
        for label, elev, grade, color, lw, ls in series:
            y = elev if key == "elev" else 100 * grade
            ax.plot(miles, y, label=label, color=color, lw=lw, ls=ls)
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper left", fontsize=9)

    for first, last in ARTIFACTS.values():
        for ax in (ax_elev, ax_grade):
            ax.axvspan(miles[first], miles[last], color="C3", alpha=0.12, lw=0)

    ax_grade.axhline(0, color="k", lw=0.5)
    ax_grade.set_xlabel("distance (miles)")
    ax_elev.set_title("I-80 north across the Carquinez Strait (artifacts shaded)")
    fig.tight_layout()
    plt.show()

    """
    ## When not to reach for `BridgeFilter`

    A real valley is also "a span that sits below the road on both sides", and
    nothing in the geometry distinguishes it from a bridge. `baseline_radius_ft`
    is what draws the line, and its one-mile default is only right for gentle
    terrain — [How Filtration Works](02_filtering_example) shows that same
    default erasing 1.5 miles of genuine canyon on the Colorado trace.

    The rule that follows: set the radius to the spans you are correcting, and
    always diff filtered against raw across the whole trace before trusting it.
    """


if __name__ == "__main__":
    main()
