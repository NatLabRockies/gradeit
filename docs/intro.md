# GradeIT

**Road Grade Inference Tool** — add elevation and road grade to GPS points.

GradeIT is a Python package from the National Laboratory of the Rockies. Give it GPS coordinates.
It gets elevation from the [USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep), filters the elevation profile, and
calculates road grade. It is for vehicles on paved roads.

```python
from gradeit import gradeit

result = gradeit(trace)

result.grade_dec_filtered  # decimal road grade (rise/run), per point
result.elevation_ft_filtered  # cleaned elevation, feet
result.elevation_ft  # the raw DEM lookup, always preserved
```

## The problem this solves

The USGS DEM is a **bare-earth** model. It shows the ground, not the road surface. A bridge across
a river returns the elevation of the water. A viaduct across a valley returns the valley floor.

These values create grade spikes that no vehicle drove. In
[Bare-Earth Bridges](examples/03_bridges_example), the raw DEM gives an **89% grade** on Interstate
80. Wood et al. (2014) say that these artifacts are unsuitable for vehicle simulation.

GradeIT removes these artifacts and preserves the nearby terrain. This is difficult because a
bridge and a valley can have the same shape. The default filter uses the five-step method from
[Wood et al. (2014)](methodology).

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

If you use GradeIT in published work, please cite the software:

> National Laboratory of the Rockies. _GradeIT: Road Grade Inference Tool_ (version 0.2.0)
> [Computer software]. https://github.com/NREL/gradeit

```bibtex
@software{gradeit,
  title    = {{GradeIT}: Road Grade Inference Tool},
  author   = {{National Laboratory of the Rockies}},
  version  = {0.2.0},
  url      = {https://github.com/NREL/gradeit},
  license  = {BSD-3-Clause}
}
```

The repository also carries a
[`CITATION.cff`](https://github.com/NREL/gradeit/blob/main/CITATION.cff), which GitHub renders as
"Cite this repository".

GradeIT uses a filter method from a separate publication. Cite
[Wood et al. (2014)](methodology) if you use the method.
