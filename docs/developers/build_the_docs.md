# Building the Docs

This site is built with [Jupyter Book](https://jupyterbook.org) 1.x.

```bash
pixi install -e docs
pixi run -e docs docs_build
```

Then open `docs/_build/html/index.html`. Other tasks:

```bash
pixi run -e docs docs_convert  # just regenerate the notebooks
pixi run -e docs docs_clean    # remove docs/_build
```

Without pixi:

```bash
pip install ".[docs]"
python docs/examples/_convert_examples_to_notebooks.py
jupyter-book build docs/
```

```{warning}
Pin Jupyter Book to `>=1.0,<2.0`. Version 2 is a ground-up rewrite on the MyST engine with a
different configuration schema — no `_toc.yml`, no Sphinx `autodoc` — so an unpinned install
produces a completely different and broken build.
```

## How examples become pages

Examples are written as **plain Python scripts** in `docs/examples/`, not as notebooks. A
converter turns each into an `.ipynb` at build time, and Jupyter Book executes it.

That indirection buys two things: the examples are diffable and reviewable as ordinary Python, and
the same file runs directly as a script — which CI does, so a broken example fails the test run
rather than the docs deploy.

The convention, enforced by `docs/examples/_convert_examples_to_notebooks.py`:

```python
"""
# Page Title

The module docstring becomes the first markdown cell, so its heading titles the page.
"""


def main():
    import numpy as np

    """
    ## A section

    Triple-quoted strings inside `main()` become markdown cells. Code between
    them becomes code cells.
    """

    x = np.arange(10)
    print(x.sum())


if __name__ == "__main__":
    main()
```

Rules:

- The filename must end in **`_example.py`** — that is the converter's glob. Files starting with
  `_` are helpers and are skipped.
- All code lives inside `def main():`. The converter strips the `def` line, the
  `if __name__ == "__main__":` guard, and the `main()` call, dedenting the body by four spaces.
- **Never use `return` inside `main()`.** Once the wrapper is stripped, a bare `return` is a
  syntax error at notebook top level.
- Put imports **inside** `main()`. This keeps `ruff` happy (no `E402`) and keeps them in the first
  code cell where a reader expects them.
- To display a value, end a cell with the bare expression, as in a notebook.

Generated `.ipynb` files are gitignored — the `.py` is the source of truth.

Add a new page by writing the file and adding it to `docs/_toc.yml` **without** the extension:

```yaml
- file: examples/06_my_example
```

## Notebooks are executed on every build

`_config.yml` sets `execute_notebooks: force` and `nb_execution_raise_on_error: true`, so every
number and figure on the site comes from actually running the code, and a failing example fails
the build instead of publishing a page with a traceback in it.

This is only safe because the examples are offline and deterministic — they read the small
committed DEM crops in `docs/data/`, never the network. **Do not call `USGSApi` from an example:**
it issues one HTTP request per point, which would both make the build flaky and hammer a public
service. Document it on a prose page instead.

```{warning}
**Do not set `MPLBACKEND=Agg` when building the docs.** The notebook kernel inherits it, which
disables inline figure capture — the build still succeeds, but every matplotlib plot silently
vanishes from the published pages. `Agg` belongs only in the CI job that runs the examples as
plain scripts, where there is no kernel and nothing to capture.
```

## The sample data

The examples run against corridor crops of two real USGS tiles, committed under `docs/data/`
(440 KB in place of 900 MB). Within those corridors the values are bit-for-bit the source data.
See [`docs/data/README.md`](https://github.com/NREL/gradeit/blob/main/docs/data/README.md).

Regenerating requires the full source tiles, which are not in the repository:

```bash
pixi run -e dev python scripts/make_docs_data.py --source-dir /path/to/tiles
```

The script verifies each crop against the full tile before writing it, and refuses to write if
they disagree. Trace slice bounds live in the `DEMOS` table at the top of the script — change one
and you must regenerate, or the crop and the trace will no longer line up.

## The API reference

`docs/api_docs.rst` is hand-written, with one `automodule` block per public module. Sphinx
`autodoc` pulls the docstrings, so **docstrings in the package are published documentation** — a
stale file path or a wrong default in a docstring is a stale or wrong docs page.

Adding a new public module means adding a block to that file; it is not automatic.

## Deployment

`.github/workflows/deploy-docs.yaml` builds the book on every pull request that touches `docs/`,
`gradeit/`, or `pyproject.toml`, and publishes to the `gh-pages` branch on push to `main`. PRs
build but do not deploy, so a broken notebook is caught before merge.

Because the API reference is generated from docstrings, that workflow watches `gradeit/**` as well
as `docs/**` — otherwise a docstring fix would never reach the site.
