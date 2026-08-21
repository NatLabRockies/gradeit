# Building the Docs

This site is built with [Jupyter Book](https://jupyterbook.org) 1.x.

```bash
pixi install -e docs
pixi run -e docs docs_build
```

Then open `docs/_build/html/index.html`. Other commands:

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

Examples are **plain Python scripts** in `docs/examples/`, not notebooks. A converter creates an
`.ipynb` file for each script during the build. Jupyter Book runs each notebook.

This design has two benefits. You can review example changes as Python code. CI can run each file as
a script. A broken example fails tests before documentation deployment.

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

- The filename must end with **`_example.py`**. This is the converter glob. Files that start with
  `_` are helpers and are skipped.
- Put all code inside `def main():`. The converter removes the `def` line, the
  `if __name__ == "__main__":` guard, and the `main()` call. It removes four spaces from the body.
- **Do not use `return` in `main()`.** After the converter removes the wrapper, a bare `return` is
  a syntax error at notebook top level.
- Put imports **inside** `main()`. This avoids `ruff` `E402` errors. Imports occur in the first
  code cell.
- To display a value, end a cell with the bare expression, as in a notebook.

Generated `.ipynb` files are gitignored. The `.py` file is the source.

Add a new page by writing the file and adding it to `docs/_toc.yml` **without** the extension:

```yaml
- file: examples/06_my_example
```

## Notebooks are executed on every build

`_config.yml` sets `execute_notebooks: force` and `nb_execution_raise_on_error: true`. The build
runs code for every number and figure. A failing example fails the build.

Examples are offline and deterministic. They read small DEM crops from `docs/data/`. They do not
use the network. **Do not call `USGSApi` from an example.** Even though it batches its
requests, it still depends on a public service, which would make the build unreliable. Document it in a prose page.

```{warning}
**Do not set `MPLBACKEND=Agg` when you build documentation.** The notebook kernel inherits this
setting. It disables inline figure capture. The build succeeds, but published matplotlib plots do
not appear. Use `Agg` only for CI that runs examples as scripts.
```

## The sample data

Examples use corridor crops from two real USGS tiles in `docs/data/`. They need 440 KB instead of
900 MB. Values in these corridors are identical to source data.
See [`docs/data/README.md`](https://github.com/NREL/gradeit/blob/main/docs/data/README.md).

Regenerating requires the full source tiles, which are not in the repository:

```bash
pixi run -e dev python scripts/make_docs_data.py --source-dir /path/to/tiles
```

The script checks each crop against the full tile before it writes data. It refuses to write if
they differ. The `DEMOS` table at the top of the script has trace slice bounds. Regenerate data
after you change a bound.

## The API reference

`docs/api_docs.rst` is hand-written. It has one `automodule` block for each public module. Sphinx
`autodoc` gets docstrings. **Package docstrings are published documentation.** Update incorrect
paths and defaults in docstrings.

Adding a new public module means adding a block to that file; it is not automatic.

## Deployment

`.github/workflows/deploy-docs.yaml` builds the book for each pull request that changes `docs/`,
`gradeit/`, or `pyproject.toml`. A push to `main` publishes to `gh-pages`. Pull requests build but
do not publish. This finds broken notebooks before merge.

The API reference uses docstrings. Therefore, this workflow watches `gradeit/**` and `docs/**`.
