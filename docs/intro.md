# GradeIT

**Road Grade Inference Tool** — add elevation and road grade to GPS points.

GradeIT is a Python package from the National Laboratory of the Rockies.
It takes GPS coordinates as input and returns the corresponding elevation and road grade.
It gets elevation from the [USGS Digital Elevation Model](https://www.usgs.gov/core-science-systems/ngp/3dep), filters the elevation profile, and
calculates road grade.
The typical and tested application for this is to add elevation and road grade information to vehicle telematics data.

```python
from gradeit import gradeit

result = gradeit(trace)

result.grade_dec_filtered  # decimal road grade (rise/run), per point
result.elevation_ft_filtered  # cleaned elevation, feet
result.elevation_ft_unfiltered  # the raw DEM lookup, always preserved
```

## The problem this solves

Vehicle telematics data might collect GPS elevation data but these signals are often noisy and unreliable for calculating accurate road grade.

To compensate for this, we can reference collected elevation data from a digital elevation model, but it comes with own challenges.

Namely, in GradeIT, we use a bare-earth digital elevation model.
It shows the elevation of the ground, not the road surface, creating artifacts that need to be corrected.

GradeIT removes these artifacts and preserves the nearby terrain.

Take a look at [the methodology](methodology) for more details.

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
> [Computer software]. https://github.com/NatLabRockies/gradeit

```bibtex
@software{gradeit,
  title    = {{GradeIT}: Road Grade Inference Tool},
  author   = {{National Laboratory of the Rockies}},
  version  = {0.2.0},
  url      = {https://github.com/NatLabRockies/gradeit},
  license  = {BSD-3-Clause}
}
```

The repository also carries a
[`CITATION.cff`](https://github.com/NatLabRockies/gradeit/blob/main/CITATION.cff), which GitHub renders as
"Cite this repository".
