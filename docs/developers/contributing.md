# Contributing

## Environment

The project uses [pixi](https://pixi.sh) for development environments and tasks. After you
[installing pixi](https://pixi.sh/latest/#installation):

```bash
pixi install -e dev
```

`pyproject.toml` defines environments under `[tool.pixi.environments]`:

- **`dev`** — the toolchain plus the `pandas` and `plot` extras. Everything below runs here.
- **`docs`** — `dev` plus Jupyter Book. See [Building the Docs](build_the_docs).

## The check task

This command runs all CI checks:

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

Run individual tasks with `pixi run -e dev test` or `pixi run -e dev typing`.

A [pre-commit](https://pre-commit.com) hook runs `check` for each commit:

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

Tests use `unittest.TestCase` classes and run with pytest. Tests are offline. The USGS API test is
skipped by default. Elevation tests use a 4 KB synthetic GeoTIFF fixture at
`tests/fixtures/n40w105/`. Regenerate it with:

```bash
pixi run -e dev python scripts/make_test_fixture.py
```

The fixture is a deterministic linear ramp. Nearest-neighbor values are known exactly. Bilinear
interpolation of this field is also exact. Sampling tests can use exact values.

## Conventions

Keep these codebase rules:

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

The default filter follows Wood et al. (2014), NLR/TP-5400-61109. If you change filtering or
grade calculation, compare it with the paper. [Methodology](../methodology) maps the five steps to
the code.

The paper has no numeric parameter values. Package defaults are package choices. If you change a
default, update the class docstring. The [API Reference](../api_docs) shows this docstring.

## Documentation

Prose and examples are in `docs/`. The documentation build runs all examples. A broken example
fails the build. See [Building the Docs](build_the_docs).
