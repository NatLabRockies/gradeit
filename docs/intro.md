# GradeIT

**Road Grade Inference Tool** — append elevation and road grade to a sequence of GPS points.

GradeIT is a Python package developed by the National Laboratory of the Rockies. Give it a
sequence of GPS coordinates and it looks up elevation from the
[USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep), cleans the
elevation profile, and derives road grade — typically for vehicles traveling on paved roads,
where grade drives energy consumption.

```python
from gradeit import gradeit

result = gradeit(trace)

result.grade_dec_filtered  # decimal road grade (rise/run), per point
result.elevation_ft_filtered  # cleaned elevation, feet
result.elevation_ft  # the raw DEM lookup, always preserved
```

## The problem this solves

Looking up elevation is the easy part. The hard part is that the USGS DEM is a **bare-earth**
model: it describes the ground, not the road surface. Where a road crosses a river on a bridge,
the DEM reports the water. Where it crosses a valley on a viaduct, the DEM reports the valley
floor.

Differentiating that to get grade produces spikes of tens of percent that no vehicle ever drove.
On the sample trace in [Bare-Earth Bridges](examples/03_bridges_example), the raw DEM implies an
**89% grade** on Interstate 80. Wood et al. (2014) note these artifacts are "unsuitable for
downstream vehicle simulation programs."

GradeIT's job is to remove them without flattening the real terrain around them — which is
harder than it sounds, because a bridge and a valley look identical to a naive detector. The
default filter implements the five-step routine from
[Wood et al. (2014)](methodology), and it is what you get if you pass nothing.

## Where to go

| If you want to…                          | Read                                                                   |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| Install it                               | [Installation](installation)                                           |
| See the shortest path to a grade profile | [Quickstart](quickstart)                                               |
| Get elevation data on your machine       | [Elevation Data](elevation_data)                                       |
| Watch it work on a real trace            | [Your First Grade Profile](examples/01_basic_example)                  |
| Understand what the filter does          | [How Filtration Works](examples/02_filtering_example)                  |
| Deal with bridges and overpasses         | [Bare-Earth Bridges](examples/03_bridges_example)                      |
| Plug in your own elevation source        | [Custom Elevation Sources](examples/05_custom_elevation_model_example) |
| Look up a class or function              | [API Reference](api_docs)                                              |

## Citation

> Wood, Eric, E. Burton, A. Duran, and J. Gonder. _Appending High-Resolution Elevation Data to
> GPS Speed Traces for Vehicle Energy Modeling and Simulation._ NREL/TP-5400-61109. National
> Renewable Energy Laboratory, Golden, CO (United States), 2014.
