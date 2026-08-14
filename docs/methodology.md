# Methodology

GradeIT's default filtration implements the five-step routine of Wood et al. (2014).

> Wood, Eric, E. Burton, A. Duran, and J. Gonder. _Appending High-Resolution Elevation Data to
> GPS Speed Traces for Vehicle Energy Modeling and Simulation._ NREL/TP-5400-61109. National
> Renewable Energy Laboratory, Golden, CO (United States), 2014.

```{note}
That is the reference for the **method**. To cite the **software**, see the Citation section on
the [home page](intro) — the two are separate, and citing the paper does not credit this package
or its authors.
```

```{image} imgs/grade_filters.png
:alt: The five-step filtration routine from Wood et al. (2014)
:width: 100%
```

## The five steps

Step A is the raw input. `Wood2014Filter` carries out steps B through E.

| Step  | What happens                                                                                                                           |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **A** | Raw elevation versus distance, straight from the DEM.                                                                                  |
| **B** | Elevation is downsampled onto a uniformly spaced **distance** grid, each node carrying the **median** of the raw points falling in it. |
| **C** | The downsampled profile passes through a combined **Savitzky-Golay and binomial** filter, and the pre/post difference is computed.     |
| **D** | Nodes whose filtration residual exceeds a threshold are **discarded and backfilled** by interpolation.                                 |
| **E** | The backfilled profile is filtered again, then elevation at the **original** distance values is recovered by interpolation.            |

Grade is then computed as the derivative of the final filtered elevation with respect to
distance, matching the paper's definition. GradeIT always recomputes grade from the final
elevation, so the two can never drift apart.

## Why step B is the load-bearing one

GPS traces are sampled in **time**. Their spacing in **distance** therefore varies with vehicle
speed — and it varies a lot. On the 250-point Colorado trace used throughout these examples,
median point spacing is 133 ft while the 5th and 95th percentiles are 51 ft and 370 ft, with
individual gaps from 10 ft to 840 ft.

Smoothing that signal by point index gives a filter whose physical cutoff swings sevenfold along
a single trace: aggressive where the vehicle crawled, barely present where it sped up. Resampling
onto a fixed distance grid first makes the cutoff a fixed number of feet everywhere, which is why
the paper specifies steps C–E on the uniform grid rather than on the original samples.

This is also why every `Wood2014Filter` parameter is declared in feet rather than in samples.
`SavitzkyGolayFilter`, which smooths in the index domain, is retained for backward compatibility
but superseded for exactly this reason.

## Why the residual, not the drop

Step D discards points by **filtration residual** — the difference between a node and its own
smoothed value — rather than by how far elevation drops.

That distinction matters more than it looks. A smoother is itself dragged toward an artifact, so
a 55 ft bridge drop leaves a residual of only about 11 ft. Setting the threshold to the "tens of
feet" the paper attributes to the raw artifact would catch nothing at all. GradeIT's 8 ft default
is the DEM's own stated 2.44 m vertical RMSE: a residual larger than the elevation model's
1-sigma accuracy is not explainable as DEM noise.

It also explains a structural limit. A residual detector is blind to any feature **wider than its
own smoothing kernel**, because the smoother simply follows a wide feature down and the residual
collapses. That is why no amount of widening `savgol_window_ft` will remove a mile-long bridge —
see [Bare-Earth Bridges](examples/03_bridges_example), where widening the window instead drags
the road below sea level.

## The paper specifies no numeric values

This is worth stating plainly: **Wood et al. give no parameter values** — not the grid interval,
not the filter widths, not the discard threshold. The defaults in `Wood2014Filter` are this
package's choices, reasoned from the DEM's ~33 ft post spacing and 2.44 m vertical RMSE and
documented parameter by parameter in the class docstring and in [Filters](filters).

They are a considered starting point, not a reproduction of the paper's own settings, which are
not published. Treat them as such if your traces differ substantially from highway driving over
1/3 arc-second terrain.

## Bare-earth bridges and overpasses

The USGS DEM is a bare-earth product: road infrastructure is not in it. Where a road crosses a
river, a valley, or another road, the model describes what is underneath the bridge rather than
the deck.

Step D catches these incidentally — a bare-earth artifact is simply a large filtration residual,
so the routine removes it without any bridge-specific logic. That covers the common case of
culverts, creek crossings, and ordinary overpasses.

For spans wider than the smoothing kernel can see, `BridgeFilter` attacks the problem differently,
comparing each point against a two-sided rolling-maximum baseline instead of against a smoothed
version of itself. It reaches artifacts the residual method structurally cannot — at the cost of
needing to be told, through `baseline_radius_ft`, what scale of span counts as a bridge.

That parameter is doing real work, because **a valley is also a span that sits below the road on
both sides**. Nothing in the geometry separates the two cases; the radius is what draws the line.
Both failure modes are demonstrated on real traces in
[How Filtration Works](examples/02_filtering_example) and
[Bare-Earth Bridges](examples/03_bridges_example).
