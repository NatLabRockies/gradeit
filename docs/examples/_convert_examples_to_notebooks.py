"""Convert the plain-Python docs examples into notebooks for Jupyter Book.

Each ``*_example.py`` in this directory is written so that it can be *both* run
directly (``python docs/examples/01_basic_example.py``, which CI does, so a
broken example fails the test run rather than the docs deploy) and rendered as a
notebook page.

The convention:

* the module docstring becomes the first markdown cell, so its ``# Heading`` is
  the page title;
* all the code lives inside ``def main():``;
* string literals standing alone as statements **directly** in ``main``'s body
  become markdown cells, and the code between them becomes code cells;
* the file ends with the usual ``if __name__ == "__main__": main()`` guard, which
  is dropped along with the ``def main():`` wrapper.

Parsing is done with :mod:`ast` rather than by scanning for triple quotes,
because a line-based scanner cannot tell a markdown block from a nested
function's docstring -- it would split that function's body across two cells and
emit a notebook that does not parse. Working from the syntax tree means only
statement-position strings at the top level of ``main`` are treated as prose;
docstrings on nested defs and classes stay where they belong, in the code.

Cells are sliced out of the original source by line number instead of being
unparsed from the tree, so comments and blank-line grouping survive the round
trip -- in these examples the comments carry a good share of the explanation.

Run it from the repository root::

    python docs/examples/_convert_examples_to_notebooks.py
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import List

import nbformat

HERE = Path(__file__).resolve().parent
KERNELSPEC = {"display_name": "Python 3", "language": "python", "name": "python3"}


def _is_markdown(node: ast.stmt) -> bool:
    """True for a bare string literal used as a statement."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def script_to_notebook(script_path: Path, notebook_path: Path) -> None:
    source = script_path.read_text()
    lines = source.splitlines()
    module = ast.parse(source)

    cells: List[nbformat.NotebookNode] = []

    docstring = ast.get_docstring(module, clean=False)
    if docstring:
        cells.append(nbformat.v4.new_markdown_cell(textwrap.dedent(docstring).strip()))

    try:
        main = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
    except StopIteration:
        raise SystemExit(f"{script_path}: no 'def main():' found")

    def add_code(start: int, end: int) -> None:
        """Emit lines[start:end] as a code cell, dedented."""
        chunk = textwrap.dedent("\n".join(lines[start:end])).strip("\n")
        if chunk.strip():
            cells.append(nbformat.v4.new_code_cell(chunk))

    # Start just after the signature, but keep any comments that lead the body.
    cursor = main.body[0].lineno - 1
    while cursor > main.lineno and lines[cursor - 1].strip().startswith("#"):
        cursor -= 1

    for node in main.body:
        if not _is_markdown(node):
            continue
        add_code(cursor, node.lineno - 1)
        assert isinstance(node.value, ast.Constant)
        cells.append(nbformat.v4.new_markdown_cell(textwrap.dedent(node.value.value).strip()))
        cursor = node.end_lineno or node.lineno

    add_code(cursor, main.end_lineno or len(lines))

    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata["kernelspec"] = KERNELSPEC
    nbformat.write(notebook, str(notebook_path))


def main() -> None:
    for example in sorted(HERE.glob("*_example.py")):
        notebook = example.with_suffix(".ipynb")
        script_to_notebook(example, notebook)
        print(f"Converted {example.name} -> {notebook.name}")


if __name__ == "__main__":
    main()
