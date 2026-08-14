# Contributing

## Environment

The project uses [pixi](https://pixi.sh) for development environments and tasks. After
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
```

Environments are declared in `pyproject.toml` under `[tool.pixi.environments]`:

- **`dev`** — the toolchain plus the `pandas` and `plot` extras. Everything below runs here.
- **`docs`** — `dev` plus Jupyter Book. See [Building the Docs](build_the_docs).

## The check task

One command runs everything CI runs:

```bash
pixi run -e dev check
```

That is format → lint → markdown → types → tests:

| Task       | Command            | Covers                            |
| ---------- | ------------------ | --------------------------------- |
| `fmt_fix`  | `ruff format`      | all Python, including `docs/`     |
| `lint_fix` | `ruff check --fix` | all Python, including `docs/`     |
| `fmt_md`   | `dprint fmt`       | all markdown, at 100 columns      |
| `typing`   | `mypy .`           | the package (`docs/` is excluded) |
| `test`     | `pytest tests/`    | the test suite                    |

Run pieces individually with `pixi run -e dev test`, `pixi run -e dev typing`, and so on.

A [pre-commit](https://pre-commit.com) hook runs `check` on every commit:

```bash
pixi run -e dev pre-commit install
```

```{note}
`ruff` lints and formats `docs/examples/*.py` along with everything else, and `dprint` reformats
every markdown file including the docs pages. If you add either, run `pixi run -e dev check`
before pushing or CI will fail on formatting.
```

## Tests

```bash
pixi run -e dev test
pixi run -e dev python -m pytest tests/test_wood2014.py -v  # one file
```

Tests use `unittest.TestCase` classes, run under pytest. They are fully offline: the one test
that would hit the USGS API is skipped by default, and elevation tests read a 4 KB synthetic
GeoTIFF fixture at `tests/fixtures/n40w105/`, regenerable with:

```bash
pixi run -e dev python scripts/make_test_fixture.py
```

That fixture is a deterministic linear ramp, chosen so nearest-neighbor values are exactly known
and bilinear interpolation of a linear field is analytically exact — which lets the sampling tests
assert exact values rather than tolerances.

## Conventions

A few rules the codebase holds to; please keep them:

- **Filter parameters are declared in physical units (feet), not sample counts.** A filter's
  behavior must not change with GPS sampling rate or vehicle speed. See
  [Methodology](../methodology).
- **Filters take and return elevation, never grade.** Grade is computed once, from the final
  filtered elevation, so the two cannot disagree.
- **Elevation is feet, grade is a decimal, distance is feet.** Names carry the unit (`_ft`,
  `_dec`).
- **Missing elevation is `NaN`**, not `None` and not a sentinel.
- **`gradeit()` never mutates its input.**
- **pandas stays optional.** It may only be imported lazily, inside the function that needs it.
  `requests` likewise — `tests/test_imports.py` asserts that `import gradeit` pulls in neither.

## Changing filtration

The default filtration follows Wood et al. (2014), NREL/TP-5400-61109. If you change filtering or
grade computation, check it against the paper — [Methodology](../methodology) maps its five steps
onto the code.

The paper specifies no numeric parameter values, so the defaults are this package's own reasoned
choices. If you change one, update the reasoning in the class docstring along with it; that
docstring is rendered into the [API Reference](../api_docs).

## Documentation

Prose and examples live in `docs/`. The examples are executed on every docs build, so a change
that breaks one fails the build. See [Building the Docs](build_the_docs).
