"""Sphinx configuration for the pytakeoff documentation."""

import os
import sys

# Make the package importable for autodoc (docs/ is one level below the root).
sys.path.insert(0, os.path.abspath("../src"))

from pytakeoff import __version__  # noqa: E402

# -- Project information ---------------------------------------------------
project = "pytakeoff"
author = "Takeoff Technologies"
copyright = "2026, Takeoff Technologies"
release = __version__
version = __version__

# -- General configuration -------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",       # pull docstrings from the source
    "sphinx.ext.napoleon",      # tolerate Google/NumPy-style sections too
    "sphinx.ext.intersphinx",   # link to the stdlib / requests docs
    "sphinx.ext.viewcode",      # add [source] links
    "myst_parser",              # write narrative pages in Markdown
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Markdown (MyST) niceties for the narrative pages.
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

# -- Autodoc ---------------------------------------------------------------
autodoc_member_order = "bysource"       # match the reading order of the source
autoclass_content = "both"              # class docstring + __init__ docstring
autodoc_typehints = "description"       # render type hints in the body, not the signature
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
}
# Runtime deps that need not be importable when building docs on a bare host.
autodoc_mock_imports = ["websocket", "requests"]

# -- Intersphinx -----------------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "requests": ("https://requests.readthedocs.io/en/stable/", None),
}
# Never fail the build if an inventory can't be fetched (offline / RTD hiccup).
intersphinx_disabled_reftypes = ["*"]

# Unresolved cross-references in docstrings (e.g. :data: to private module
# constants) should warn, not break the build.
nitpicky = False

# -- HTML output -----------------------------------------------------------
html_theme = "furo"
html_title = f"pytakeoff {release}"
html_static_path = ["_static"]
