"""High-level 2D polar analysis.

The analysis is stateless on the server — every run receives its full
parameter set — so this object simply holds your parameters locally and
sends them with each :meth:`run`::

    analysis = project.analysis_2d(alpha_range=[-10, 10], reynolds_million=1.0)
    analysis.set_parameters(flap_lock=True)          # tweak any time
    result = analysis.run()                          # raw numbers
    figures = analysis.figures()                     # the web app's Plotly figures

Parameters (server defaults in parentheses):

- ``alpha_range`` ([-15, -5, 0, 5, 15]) — angles of attack, degrees
- ``reynolds_million`` (1) — Reynolds number in millions
- ``flap_range`` ([-15, -5, 0, 5, 15]) — flap angles swept per alpha
- ``flap_lock`` (False) — True for a plain alpha sweep (no flap sweep)
- ``ncrit`` (0.18) — transition criterion (0.18 water, ~9 air)
- ``mach`` (0.0)
- ``solver`` (["NN"]) — also "XFOIL", "IA", ...
- ``xtr_upper`` / ``xtr_lower`` (1.0) — forced transition locations
- ``fluid`` ("water") / ``elevation`` (0)

The sweep runs over every *visible* foil section in the project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:  # pragma: no cover
    from .client import TakeoffClient

_KNOWN_PARAMS = frozenset(
    {
        "alpha_range",
        "reynolds_million",
        "flap_range",
        "flap_lock",
        "ncrit",
        "mach",
        "solver",
        "xtr_upper",
        "xtr_lower",
        "fluid",
        "elevation",
        "entity_type",
    }
)


class Analysis2D:
    """A configured 2D polar analysis (see module docstring for parameters)."""

    def __init__(self, client: "TakeoffClient", **params: Any) -> None:
        self._client = client
        self._params: Dict[str, Any] = {}
        if params:
            self.set_parameters(**params)

    def __repr__(self) -> str:
        return f"Analysis2D({self._params!r})"

    # ------------------------------------------------------------------ #
    # Parameters

    def parameters(self) -> Dict[str, Any]:
        """The parameters that will be sent (server defaults fill the rest)."""
        return dict(self._params)

    def set_parameters(self, **params: Any) -> Dict[str, Any]:
        """Set one or more analysis parameters; returns the full current set.

        Unknown parameter names raise ``ValueError`` (typo protection).
        Pass ``None`` to remove a parameter and fall back to the server
        default.
        """
        unknown = set(params) - _KNOWN_PARAMS
        if unknown:
            raise ValueError(
                f"Unknown analysis parameter(s): {sorted(unknown)}. "
                f"Known: {sorted(_KNOWN_PARAMS)}"
            )
        for key, value in params.items():
            if value is None:
                self._params.pop(key, None)
            else:
                self._params[key] = value
        return self.parameters()

    # ------------------------------------------------------------------ #
    # Running

    def run(self) -> Dict[str, Any]:
        """Run the sweep and return the raw numbers (no plots).

        One entry per visible section, parallel arrays with one value per
        computed sweep point; unconverged points are ``None``. Chordwise
        variables (``top_Cp``/``bot_Cp`` with ``top_x``/``bot_x``) carry one
        array per sweep point::

            {"sections": [{"section": name, "n_points": N,
                           "data": {"alpha": [...], "Cl": [...], "Cd": [...],
                                    "Cl_Cd": [...], ...,
                                    "top_x": [[...], ...], "top_Cp": [[...], ...]}}],
             "variables": ["alpha", "Cl", ...]}
        """
        return self._client.call("get_polar_data", self._params)

    def figures(self, **extra: Any) -> List[Dict[str, Any]]:
        """Run the sweep and return the web app's ready-made Plotly figures.

        ``extra`` accepts the plot-only options (``plotting_mode``,
        ``foil_section_graphic_request``, ``dark_mode``).
        """
        payload = {**self._params, **extra}
        result = self._client.call("update_polar_plot", payload)
        return result.get("plotly_graphics", [])
