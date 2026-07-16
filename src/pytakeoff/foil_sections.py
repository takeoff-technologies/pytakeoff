"""High-level handle for FoilSection entities.

Obtained from a project::

    section = project.foil_section("main")        # by name
    sections = project.foil_sections()            # all of them

Three groups of state, each with a getter and a setter:

- **Control points** — the B-spline that IS the section shape.
- **Geometric parameters** — thickness, camber, LE radius, TE thickness,
  TE angle. Setting one re-derives the control points parametrically.
- **Structural parameters** — area, Ixx, section modulus, torsion constant
  (and the read-only centroid). Also parametric on write.

Getters always fetch live values from the server (the GUI may be editing
the same session). Setters send the update and return the resulting
values — parametric setters refit the B-spline, so the achieved value can
differ slightly from the requested one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from .exceptions import CommandError

if TYPE_CHECKING:  # pragma: no cover
    from .client import TakeoffClient

#: python kwarg -> server key, geometric parameters (group "geometry_properties")
_GEOMETRY_KEYS = {
    "tc": "tc",
    "camber": "camber",
    "le_radius": "LE_radius",
    "te_thickness": "TE_thickness",
    "te_angle": "TE_angle",
}

#: python kwarg -> server key, structural parameters (group "structural_properties")
_STRUCTURE_KEYS = {
    "area": "area",
    "Ixx": "Ixx",
    "SMx": "SMx",
    "J": "J",
}


class FoilSection:
    """One foil section in the currently open project."""

    def __init__(self, client: "TakeoffClient", data: Dict[str, Any]) -> None:
        self._client = client
        self.id: Optional[str] = data.get("id")
        self.name: Optional[str] = data.get("name")

    def __repr__(self) -> str:
        return f"FoilSection({self.name!r}, id={self.id!r})"

    # ------------------------------------------------------------------ #
    # Wire helpers

    def _get(self, groups: List[str]) -> Dict[str, Any]:
        return self._client.call(
            "get_entity",
            {"entity_type": "FoilSection", "data": {"id": self.id}, "groups": groups},
        )

    def _update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # No `groups` on updates: the fields present in the payload determine
        # what gets updated; groups are only for requesting data on reads.
        return self._client.call(
            "update_entity",
            {"entity_type": "FoilSection", "data": {"id": self.id, **data}},
        )

    # ------------------------------------------------------------------ #
    # Control points

    def control_points(self) -> Dict[str, Any]:
        """The section's B-spline: ``{"upper", "lower", "degree", "n_coefs"}``.

        ``upper`` / ``lower`` are ``[[x, y], ...]`` control-point lists.
        """
        geo = self._get(["control_points"]).get("foil_section_geometry", {})
        return {
            "upper": geo.get("upper_coefs"),
            "lower": geo.get("lower_coefs"),
            "degree": geo.get("degree"),
            "n_coefs": geo.get("n_coefs"),
        }

    def set_control_points(
        self,
        upper: Optional[Sequence[Sequence[float]]] = None,
        lower: Optional[Sequence[Sequence[float]]] = None,
    ) -> Dict[str, Any]:
        """Replace the upper and/or lower control points and rebuild.

        Returns the control points as stored by the server.
        """
        geometry: Dict[str, Any] = {}
        if upper is not None:
            geometry["upper_coefs"] = [list(p) for p in upper]
        if lower is not None:
            geometry["lower_coefs"] = [list(p) for p in lower]
        if not geometry:
            raise ValueError("Pass upper= and/or lower= control points")
        self._update({"foil_section_geometry": geometry})
        return self.control_points()

    def n_control_points(self) -> Optional[int]:
        """Number of control points per side (upper and lower share the count)."""
        return self.control_points().get("n_coefs")

    def control_point(self, index: int, side: str = "upper") -> Sequence[float]:
        """One control point ``[x, y]`` by index from the given side.

        ``side`` is ``"upper"`` or ``"lower"``. Negative indices count from
        the end, as in a Python list.
        """
        coefs = self._side_coefs(side)
        try:
            return coefs[index]
        except IndexError:
            raise IndexError(
                f"control point index {index} out of range for the {side} side "
                f"(0..{len(coefs) - 1})"
            ) from None

    def set_control_point(
        self, index: int, point: Sequence[float], side: str = "upper"
    ) -> Dict[str, Any]:
        """Replace a single control point (by index, on one side) and rebuild.

        Reads the current control net, swaps the point at ``index`` on
        ``side`` (``"upper"`` or ``"lower"``) for ``point`` (an ``[x, y]``
        pair), and sends the whole side back. Returns the control points as
        stored by the server (see :meth:`control_points`).
        """
        coefs = [list(p) for p in self._side_coefs(side)]
        try:
            coefs[index] = [float(point[0]), float(point[1])]
        except IndexError:
            raise IndexError(
                f"control point index {index} out of range for the {side} side "
                f"(0..{len(coefs) - 1})"
            ) from None
        return self.set_control_points(**{side: coefs})

    def _side_coefs(self, side: str) -> List[Sequence[float]]:
        if side not in ("upper", "lower"):
            raise ValueError(f"side must be 'upper' or 'lower', got {side!r}")
        coefs = self.control_points().get(side)
        if not coefs:
            raise CommandError(f"No {side} control points available for this section")
        return coefs

    # ------------------------------------------------------------------ #
    # Geometric parameters

    def geometry(self) -> Dict[str, Any]:
        """Geometric parameters: ``{"tc", "camber", "le_radius", "te_thickness", "te_angle"}``."""
        props = self._get(["geometry_properties"]).get("foil_section_properties", {})
        return {py: props.get(srv) for py, srv in _GEOMETRY_KEYS.items()}

    def set_geometry(
        self,
        *,
        tc: Optional[float] = None,
        camber: Optional[float] = None,
        le_radius: Optional[float] = None,
        te_thickness: Optional[float] = None,
        te_angle: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Set one or more geometric parameters (parametric refit).

        Returns the resulting geometric parameters — the achieved values,
        which may differ slightly from the requested ones.
        """
        requested = {
            "tc": tc,
            "camber": camber,
            "le_radius": le_radius,
            "te_thickness": te_thickness,
            "te_angle": te_angle,
        }
        props = {
            _GEOMETRY_KEYS[key]: value
            for key, value in requested.items()
            if value is not None
        }
        if not props:
            raise ValueError("Pass at least one geometric parameter")
        self._update({"foil_section_properties": props})
        return self.geometry()

    # ------------------------------------------------------------------ #
    # Structural parameters

    def structure(self) -> Dict[str, Any]:
        """Structural parameters: ``{"area", "centroid", "Ixx", "SMx", "J"}``.

        ``centroid`` is read-only (computed); the others can be set with
        :meth:`set_structure`.
        """
        props = self._get(["structural_properties"]).get("foil_section_properties", {})
        result = {py: props.get(srv) for py, srv in _STRUCTURE_KEYS.items()}
        result["centroid"] = props.get("centroid")
        return result

    def set_structure(
        self,
        *,
        area: Optional[float] = None,
        Ixx: Optional[float] = None,
        SMx: Optional[float] = None,
        J: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Set one or more structural parameters (parametric refit).

        Returns the resulting structural parameters.
        """
        requested = {"area": area, "Ixx": Ixx, "SMx": SMx, "J": J}
        props = {
            _STRUCTURE_KEYS[key]: value
            for key, value in requested.items()
            if value is not None
        }
        if not props:
            raise ValueError("Pass at least one structural parameter")
        self._update({"foil_section_properties": props})
        return self.structure()

    # ------------------------------------------------------------------ #
    # Coordinates

    def points(self) -> Any:
        """The section's outline coordinates (computed from the B-spline)."""
        return self._get(["points"]).get("foil_section_geometry", {}).get("points")
