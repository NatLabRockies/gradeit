# Methodology

The default GradeIT filter uses the five-step method from Wood et al. (2014).

> Wood, Eric, E. Burton, A. Duran, and J. Gonder. _Appending High-Resolution Elevation Data to
> GPS Speed Traces for Vehicle Energy Modeling and Simulation._ NLR/TP-5400-61109. National
> Laboratory of the Rockies, Golden, CO (United States), 2014.

```{note}
This paper is the reference for the **method**. To cite the **software**, see Citation on the
[home page](intro). These are separate references.
```

```{image} imgs/grade_filters.png
:alt: The five-step filtration routine from Wood et al. (2014)
:width: 100%
```

## The five steps

Step A is the raw input. `Wood2014Filter` does steps B through E.

| Step  | What happens                                                                                                                |
| ----- | --------------------------------------------------------------------------------------------------------------------------- |
| **A** | Raw elevation versus distance, straight from the DEM.                                                                       |
| **B** | GradeIT resamples elevation on a uniform **distance** grid. Each node has the **median** of raw points in that node.        |
| **C** | GradeIT applies a combined **Savitzky-Golay and binomial** filter. It calculates the difference before and after filtering. |
| **D** | GradeIT removes nodes with a filter residual above a threshold. It fills these nodes by interpolation.                      |
| **E** | GradeIT filters the filled profile again. It interpolates elevation at the **original** distances.                          |

## Why step B is important

GPS traces use **time** sampling. Therefore, point spacing in **distance** changes with vehicle
speed. In the 250-point Colorado trace, median spacing is 133 ft. Gaps range from 10 ft to 840 ft.

Point-index smoothing gives a filter with a different physical width at each vehicle speed.
Resampling to a fixed distance grid gives the filter a fixed width in feet. The paper therefore
uses the uniform grid for steps C–E.

## Bare-earth bridges and overpasses

The USGS DEM is a bare-earth product: road infrastructure is not in it. Where a road crosses a
river, a valley, or another road, the model describes what is underneath the bridge rather than
the road above it.

Step D finds many bare-earth artifacts because they have a large filter residual. It does not need
large bridge-specific logic. This includes culverts, creek crossings, and ordinary overpasses.

For spans wider than the smoothing kernel (think a large bridge like the Golden Gate Bridge), use `BridgeFilter`. It compares each point with a
two-sided rolling-maximum baseline. It can find artifacts that the residual method cannot find.
Set `baseline_radius_ft` to define the bridge span scale.

This parameter is important since a large valley and a large bridge can look similar to the filter.
See real traces in [How Filtration Works](examples/02_filtering_example) and
[Bare-Earth Bridges](examples/03_bridges_example).
