"""Build the examples gallery from the files in ``examples/``.

Runs at ``builder-inited``, so an example added to ``examples/`` appears in the
docs with no page written by hand: scripts become a literal include, notebooks
are unrolled into their markdown prose and code cells, and both are offered as
a download.

Everything lands in ``docs/examples/`` (generated, gitignored). The directory is
rebuilt from scratch each run, so deleted examples don't linger; the marker file
guards against wiping a directory this extension didn't create.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sphinx.application import Sphinx
from sphinx.errors import ExtensionError
from sphinx.util import logging

logger = logging.getLogger(__name__)

#: Generated pages live here, relative to the docs source dir.
OUTPUT_DIR = "examples"
#: Copies of the example files, referenced by literalinclude and download.
FILES_DIR = "_files"
#: Written into OUTPUT_DIR so a later build knows the directory is ours to wipe.
MARKER = ".generated"


def _script_title_and_intro(source: str, fallback: str) -> Tuple[str, str]:
    """Title (first docstring line) and intro (the rest) of a script."""
    try:
        docstring = ast.get_docstring(ast.parse(source)) or ""
    except SyntaxError:
        docstring = ""
    if not docstring.strip():
        return fallback, ""
    head, _, rest = docstring.strip().partition("\n")
    return head.strip().rstrip("."), rest.strip()


def _notebook_title_and_intro(cells: List[Dict[str, Any]], fallback: str) -> Tuple[str, str]:
    """Title and intro from a notebook's leading markdown cell, if it has one."""
    for cell in cells:
        if cell.get("cell_type") != "markdown":
            break
        text = "".join(cell.get("source", [])).strip()
        if text.startswith("# "):
            head, _, rest = text.partition("\n")
            return head[2:].strip(), rest.strip()
        break
    return fallback, ""


def _download(filename: str) -> str:
    return f"{{download}}`Download {filename} <{FILES_DIR}/{filename}>`"


def _script_page(path: Path) -> Tuple[str, str]:
    """(title, page body) for a ``.py`` example."""
    source = path.read_text(encoding="utf-8")
    title, intro = _script_title_and_intro(source, path.stem)
    parts = [f"# {title}", ""]
    if intro:
        parts += [intro, ""]
    parts += [
        _download(path.name),
        "",
        f"```{{literalinclude}} {FILES_DIR}/{path.name}",
        ":language: python",
        "```",
        "",
    ]
    return title, "\n".join(parts)


def _notebook_page(path: Path) -> Tuple[str, str]:
    """(title, page body) for an ``.ipynb`` example.

    The committed notebooks carry no outputs, so the cells are rendered
    directly — markdown as prose, code as copyable python blocks — rather than
    pulling in a notebook-rendering extension.
    """
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells = notebook.get("cells", [])
    title, intro = _notebook_title_and_intro(cells, path.stem)

    parts = [f"# {title}", ""]
    if intro:
        parts += [intro, ""]
    parts += [
        _download(path.name),
        "",
        "*A notebook — download it to run the cells yourself, or copy the code below.*",
        "",
    ]

    skip_first_markdown = bool(intro) or title != path.stem
    for cell in cells:
        text = "".join(cell.get("source", [])).strip()
        if not text:
            continue
        if cell.get("cell_type") == "markdown":
            if skip_first_markdown:
                skip_first_markdown = False
                continue
            parts += [text, ""]
        elif cell.get("cell_type") == "code":
            parts += ["```python", text, "```", ""]
    return title, "\n".join(parts)


def _index_page(scripts: List[Tuple[str, str]], notebooks: List[Tuple[str, str]]) -> str:
    parts = [
        "# Examples",
        "",
        "Every example below ships with the package. Copy the code straight off the",
        "page, or download the file and run it as-is.",
        "",
        "Each one authenticates with a saved API key — see [Getting started](../getting-started.md)",
        "if you have not set one up yet.",
        "",
    ]
    if scripts:
        parts += [
            "## Scripts",
            "",
            "Run top to bottom, e.g. `python 02_connect.py`.",
            "",
            "```{toctree}",
            ":maxdepth: 1",
            "",
        ]
        parts += [stem for stem, _ in scripts]
        parts += ["```", ""]
    if notebooks:
        parts += [
            "## Notebooks",
            "",
            "Meant to be stepped through cell by cell.",
            "",
            "```{toctree}",
            ":maxdepth: 1",
            "",
        ]
        parts += [stem for stem, _ in notebooks]
        parts += ["```", ""]
    return "\n".join(parts)


def _prepare_output(out: Path) -> None:
    if out.exists():
        if not (out / MARKER).is_file():
            raise ExtensionError(
                f"{out} exists but was not generated by examples_gallery "
                f"(no {MARKER} marker). Move it aside — this extension owns "
                f"that directory and rebuilds it on every build."
            )
        shutil.rmtree(out)
    (out / FILES_DIR).mkdir(parents=True)
    (out / MARKER).write_text(
        "Generated by docs/_ext/examples_gallery.py — do not edit or commit.\n",
        encoding="utf-8",
    )


def generate(app: Sphinx) -> None:
    srcdir = Path(app.srcdir)
    examples_dir = (srcdir.parent / "examples").resolve()
    out = srcdir / OUTPUT_DIR

    if not examples_dir.is_dir():
        logger.warning("examples_gallery: no examples/ directory at %s", examples_dir)
        return

    paths = sorted(
        p for p in examples_dir.iterdir()
        if p.suffix in (".py", ".ipynb") and not p.name.startswith("_")
    )
    if not paths:
        logger.warning("examples_gallery: no examples found in %s", examples_dir)
        return

    _prepare_output(out)

    scripts: List[Tuple[str, str]] = []
    notebooks: List[Tuple[str, str]] = []
    for path in paths:
        title, body = (
            _notebook_page(path) if path.suffix == ".ipynb" else _script_page(path)
        )
        (out / f"{path.stem}.md").write_text(body, encoding="utf-8")
        shutil.copyfile(path, out / FILES_DIR / path.name)
        (notebooks if path.suffix == ".ipynb" else scripts).append((path.stem, title))

    (out / "index.md").write_text(_index_page(scripts, notebooks), encoding="utf-8")
    logger.info(
        "examples_gallery: generated %d example page(s) in %s",
        len(scripts) + len(notebooks),
        out,
    )


def setup(app: Sphinx) -> Dict[str, Any]:
    app.connect("builder-inited", generate)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
