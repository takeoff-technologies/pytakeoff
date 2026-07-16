"""High-level handle for 2D optimizations (OptiAeroFoil entities).

Obtained from a project::

    opt = project.optimization_2d("my_opt")            # by name
    opts = project.optimizations_2d()                  # all of them
    opt = project.create_optimization_2d("new_opt")    # create

Typical flow::

    opt.set_config(initial_section="naca0012", solver="NN",
                   optimizer_config={"maxiter": 100, "tol": 1e-3})
    opt.set_objectives([{"func": "maxGlide", "Re": 1e6, "alpha": 4}])
    result = opt.run(on_progress=lambda pct, msg: print(pct, msg))
    opt.save_result()                                # optimized section -> project

Objectives (max 3) are dicts with SailFish's condition keys — ``func``
(``"minCd"``, ``"maxCl"``, ``"maxGlide"``, or any ``min<var>``/``max<var>``
over the polar variables), ``weight``, ``Re``, ``Vs``, ``alpha``,
``flap_angle``, ``Ncrit``, ``target_Cl``, ``solve_for`` (``"fixed"`` /
``"alpha"`` / ``"flap"``), and ``alpha_robust_range`` /
``flap_robust_range`` / ``Ncrit_robust_range``.

Constraints use the same fields as the GUI tables (operators ``">"``,
``"<"``, ``"=="``; ``value`` may be a number or ``"ref"`` to compare
against the reference section):

- geometric: ``{"name", "variable", "operator", "value"}`` — variables as
  in the GUI dropdown (``area``, ``SMx``, ``Ixx``, ``J``, ``get_tc``,
  ``get_max_camber``, ...)
- aerodynamic: ``{"name", "variable", "operator", "value", "Re", "Ncrit",
  "solve_for", "alpha", "flap_angle", "target_Cl"}`` — evaluated at that
  flow condition, flat like the GUI table (no nested ``condition`` dict).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .transport import ProgressCallback

if TYPE_CHECKING:  # pragma: no cover
    from .client import TakeoffClient


def _auto_ids(items: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    """Fill in the ``id`` the server keys entries by, if not provided."""
    out = []
    for i, item in enumerate(items):
        item = dict(item)
        if item.get("id") is None:
            item["id"] = f"{prefix}_{i + 1}"
        out.append(item)
    return out


#: aero condition fields, flat in the GUI table but nested on the wire
_AERO_CONDITION_KEYS = (
    "Re",
    "Vs",
    "alpha",
    "flap_angle",
    "Ncrit",
    "target_Cl",
    "solve_for",
    "alpha_robust_range",
    "flap_robust_range",
    "Ncrit_robust_range",
)

#: defaults the GUI seeds when adding an aero constraint row
_AERO_CONDITION_DEFAULTS = {
    "Re": 1.0e6,
    "alpha": 0,
    "flap_angle": 0,
    "Ncrit": 1.0,
    "target_Cl": 1.0,
    "solve_for": "alpha",
}


def _geo_to_wire(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry.get("name", entry.get("id")),
        "metric": entry.get("variable", entry.get("metric")),
        "operator": entry.get("operator"),
        "value": entry.get("value"),
    }


def _geo_from_wire(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": entry.get("id"),
        "variable": entry.get("metric"),
        "operator": entry.get("operator"),
        "value": entry.get("value"),
    }


def _aero_to_wire(entry: Dict[str, Any]) -> Dict[str, Any]:
    condition = dict(_AERO_CONDITION_DEFAULTS)
    condition.update(entry.get("condition") or {})
    for key in _AERO_CONDITION_KEYS:
        if key in entry:
            condition[key] = entry[key]
    return {
        "id": entry.get("name", entry.get("id")),
        "variable": entry.get("variable"),
        "operator": entry.get("operator"),
        "value": entry.get("value"),
        "condition": condition,
    }


def _aero_from_wire(entry: Dict[str, Any]) -> Dict[str, Any]:
    flat = {
        "name": entry.get("id"),
        "variable": entry.get("variable"),
        "operator": entry.get("operator"),
        "value": entry.get("value"),
    }
    condition = entry.get("condition") or {}
    for key in _AERO_CONDITION_KEYS:
        if condition.get(key) is not None:
            flat[key] = condition[key]
    return flat


class Optimization2D:
    """One 2D optimization (OptiAeroFoil) in the currently open project."""

    def __init__(self, client: "TakeoffClient", data: Dict[str, Any]) -> None:
        self._client = client
        self.id: Optional[str] = data.get("id")
        self.name: Optional[str] = data.get("name")

    def __repr__(self) -> str:
        return f"Optimization2D({self.name!r}, id={self.id!r})"

    # ------------------------------------------------------------------ #
    # Wire helpers

    def _get(self) -> Dict[str, Any]:
        return self._client.call(
            "get_entity",
            {"entity_type": "OptiAeroFoil", "data": {"id": self.id}},
        )

    def _update(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.call(
            "update_entity",
            {"entity_type": "OptiAeroFoil", "data": {"id": self.id, **fields}},
        )

    # ------------------------------------------------------------------ #
    # Configuration

    def config(self) -> Dict[str, Any]:
        """The full optimization definition, as one dict.

        Includes ``initial_section`` / ``ref_section``, ``objectives``,
        ``bounds`` / ``optimize_flap`` / flap bounds, ``constraints_geo`` /
        ``constraints_aero``, ``optimizer_config``, ``solver`` /
        ``solver_config``, ``te_thickness`` / ``te_mode``, ``fluid`` /
        ``elevation``, and the run history (``optimization_runs``,
        ``selected_run_index``).
        """
        return self._get()

    def set_config(self, **fields: Any) -> Dict[str, Any]:
        """Set any configuration fields (same names as :meth:`config`).

        Returns the resulting configuration.
        """
        if not fields:
            raise ValueError("Pass at least one configuration field")
        self._update(fields)
        return self.config()

    def objectives(self) -> List[Dict[str, Any]]:
        return self.config().get("objectives", [])

    def set_objectives(self, objectives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace the objectives (max 3; see module docstring for keys)."""
        self._update({"objectives": _auto_ids(objectives, "objective")})
        return self.objectives()

    def constraints(self) -> Dict[str, List[Dict[str, Any]]]:
        """Constraints in the GUI's table shape (see module docstring)."""
        cfg = self.config()
        return {
            "geo": [_geo_from_wire(e) for e in cfg.get("constraints_geo") or []],
            "aero": [_aero_from_wire(e) for e in cfg.get("constraints_aero") or []],
        }

    def set_constraints(
        self,
        *,
        geo: Optional[List[Dict[str, Any]]] = None,
        aero: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Replace the geometric and/or aerodynamic constraint lists.

        Entries use the same fields as the GUI tables::

            opt.set_constraints(
                geo=[{"variable": "get_tc", "operator": ">", "value": 0.10}],
                aero=[{"variable": "Cd", "operator": "<", "value": "ref",
                       "Re": 1e6, "solve_for": "alpha", "target_Cl": 1.0}],
            )

        Unset aero flow fields get the GUI's defaults; ``name`` is
        auto-assigned when omitted.
        """
        fields: Dict[str, Any] = {}
        if geo is not None:
            fields["constraints_geo"] = _auto_ids(
                [_geo_to_wire(e) for e in geo], "geo"
            )
        if aero is not None:
            fields["constraints_aero"] = _auto_ids(
                [_aero_to_wire(e) for e in aero], "aero"
            )
        if not fields:
            raise ValueError("Pass geo= and/or aero= constraint lists")
        self._update(fields)
        return self.constraints()

    # ------------------------------------------------------------------ #
    # Running & results

    def run(
        self,
        *,
        on_progress: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run the optimization as configured; blocks until it finishes.

        Pass ``on_progress(percent, message)`` to stream progress. The
        default ``timeout=None`` waits as long as it takes. Returns the
        server response — ``optimized_section_name``, full ``entity_data``
        (including the run history), ``success``.
        """
        return self._client.call(
            "run_optimization",
            entity_id=self.id,
            on_progress=on_progress,
            timeout=timeout,
        )

    def runs(self) -> List[str]:
        """Keys of the stored optimization runs, in order."""
        return [str(k) for k in self.config().get("optimization_run_keys", [])]

    def result(self, run_index: Optional[Any] = None) -> Dict[str, Any]:
        """One stored run — ``{objectives, bounds, opt_data, opt_section, run_number}``.

        Defaults to the latest run. The optimized geometry is under
        ``opt_section``; scores and per-objective values under ``opt_data``.
        """
        runs = self.config().get("optimization_runs") or []
        if isinstance(runs, dict):  # tolerate dict-keyed serialization
            runs = [
                {**v, "run_number": v.get("run_number", k)} for k, v in runs.items()
            ]
        if not runs:
            raise KeyError("This optimization has no stored runs yet")
        if run_index is None:
            return runs[-1]
        for entry in runs:
            if str(entry.get("run_number")) == str(run_index):
                return entry
        available = [str(e.get("run_number")) for e in runs]
        raise KeyError(f"No run {run_index!r}; available: {available}")

    def restore(self, run_index: Optional[str] = None) -> Dict[str, Any]:
        """Load a stored run's optimized section back as the working state."""
        payload: Dict[str, Any] = {"optimization_id": self.id}
        if run_index is not None:
            payload["run_index"] = run_index
        return self._client.call("restore_optimization_case", payload)

    def delete_runs(self, run_indices: List[Any]) -> Dict[str, Any]:
        """Delete stored runs by index."""
        return self._client.call(
            "delete_optimization_results",
            optimization_id=self.id,
            run_indices=list(run_indices),
        )

    def save_result(self, **options: Any) -> Dict[str, Any]:
        """Save the optimized section into the project as a FoilSection.

        Returns ``{section_id, section_name, ...}``.
        """
        return self._client.call(
            "save_optimization_result_to_project",
            optimization_id=self.id,
            **options,
        )
