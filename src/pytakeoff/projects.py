"""Ergonomic facade over the most common project workflows.

Everything here is thin sugar over ``client.call(...)`` — any operation
not covered can always be performed with a raw command.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .analysis import Analysis2D
from .exceptions import CommandError
from .foil_sections import FoilSection
from .optimizations import Optimization2D
from .transport import ProgressCallback

if TYPE_CHECKING:  # pragma: no cover
    from .client import TakeoffClient


def _snake(entity_type: str) -> str:
    """Convert an entity type to the server's command naming (FoilSection -> foil_section)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", entity_type).lower()


class ProjectsAPI:
    def __init__(self, client: "TakeoffClient") -> None:
        self._client = client

    def list(self) -> List[Dict[str, Any]]:
        """All projects of the logged-in user."""
        return self._client.call("list_projects").get("projects", [])

    def current(self, *, groups: Optional[List[str]] = None) -> Optional["Project"]:
        """The project currently open in the server-side session, or ``None``.

        The server keeps one session per user, shared with the web app. If your
        browser has a project open, this returns that project; if nothing is
        open (e.g. a script running on its own), it returns ``None`` — call
        :meth:`open` to set the current project.
        """
        payload: Dict[str, Any] = {"groups": groups} if groups is not None else {}
        try:
            data = self._client.call("get_current_project", payload)
        except CommandError as exc:
            if "no project" in str(exc).lower():
                return None
            raise
        return Project(self._client, data.get("name", ""), data)

    def create(self, name: str, description: str = "") -> "Project":
        """Create a new project and make it the current one."""
        data = self._client.call("create_project", name=name, description=description)
        return Project(self._client, name, data)

    def open(
        self,
        name: Optional[str] = None,
        *,
        id: Optional[str] = None,
        groups: Optional[List[str]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> "Project":
        """Load a project and make it the current one.

        Identify it by ``name`` or by ``id=`` (the ``project_id`` from
        :meth:`list`). This is how a script sets the current project when
        nothing is open yet — you do **not** need the web app running. Restores
        a draft automatically if one exists.

        (While your browser has a session open on the same account, switching
        projects from a script is refused with :class:`pytakeoff.GuiSessionActive`,
        because the script and the GUI share one project — close the browser or
        use :meth:`current` to work on whatever it already has open.)
        """
        if name is None and id is None:
            raise ValueError("Pass a project name or id=")
        if name is None:
            match = next(
                (p for p in self.list() if str(p.get("project_id")) == str(id)), None
            )
            if match is None:
                raise CommandError(
                    f"No project found with id {id!r}", command="load_project"
                )
            name = match.get("name")
        payload: Dict[str, Any] = {"name": name}
        if groups is not None:
            payload["groups"] = groups
        data = self._client.call("load_project", payload, on_progress=on_progress)
        return Project(self._client, name, data)


class Project:
    """Handle to the project currently open in the server-side session.

    The server holds one current project per user session; this object is
    a convenience wrapper, not an isolated copy.
    """

    def __init__(
        self, client: "TakeoffClient", name: str, data: Optional[Dict[str, Any]] = None
    ) -> None:
        self._client = client
        self.name = name
        #: Full project payload returned when the project was created/loaded.
        self.data = data or {}

    def __repr__(self) -> str:
        return f"Project({self.name!r})"

    # ------------------------------------------------------------------ #
    # Lifecycle

    def save(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Explicitly save the project (clears the unsaved-changes flag)."""
        payload = {"name": name} if name else {}
        return self._client.call("save_project", payload)

    def info(self, groups: Optional[List[str]] = None) -> Dict[str, Any]:
        """Current project state (entities overview, unsaved-changes flag, ...)."""
        payload = {"groups": groups} if groups is not None else {}
        return self._client.call("get_current_project", payload)

    # ------------------------------------------------------------------ #
    # Generic entity CRUD (entity_type examples: "FoilSection", "Wing",
    # "Bulb", "Hull", "Sail", "OptiAeroFoil", ...)

    def entities(
        self, entity_type: str, *, groups: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """All entities of a type in the current project.

        Uses the same typed command as the web app (e.g.
        ``get_all_foil_section``), which returns the list under a
        pluralized key (``foil_sections``).
        """
        snake = _snake(entity_type)
        payload: Dict[str, Any] = {"groups": groups} if groups is not None else {}
        result = self._client.call(f"get_all_{snake}", payload)
        return result.get(f"{snake}s", [])

    def entity(
        self,
        entity_type: str,
        *,
        id: Optional[str] = None,
        name: Optional[str] = None,
        groups: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """One entity by id or name."""
        data: Dict[str, Any] = {}
        if id is not None:
            data["id"] = id
        if name is not None:
            data["name"] = name
        payload: Dict[str, Any] = {"entity_type": entity_type, "data": data}
        if groups is not None:
            payload["groups"] = groups
        return self._client.call("get_entity", payload)

    def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.call("create_entity", entity_type=entity_type, data=data)

    def update_entity(
        self,
        entity_type: str,
        data: Dict[str, Any],
        *,
        groups: Optional[List[str]] = None,
        force_changes: bool = False,
    ) -> Dict[str, Any]:
        """Update an entity; ``data`` must include its ``id``."""
        payload: Dict[str, Any] = {
            "entity_type": entity_type,
            "data": data,
            "force_changes": force_changes,
        }
        if groups is not None:
            payload["groups"] = groups
        return self._client.call("update_entity", payload)

    def delete_entity(
        self, entity_type: str, *, id: Optional[str] = None, name: Optional[str] = None
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if id is not None:
            data["id"] = id
        if name is not None:
            data["name"] = name
        return self._client.call("delete_entity", entity_type=entity_type, data=data)

    # ------------------------------------------------------------------ #
    # Foil sections & analysis

    def foil_sections(self) -> List[FoilSection]:
        """High-level handles for every foil section in the project."""
        return [FoilSection(self._client, d) for d in self.entities("FoilSection")]

    def foil_section(
        self, name: Optional[str] = None, *, id: Optional[str] = None
    ) -> FoilSection:
        """One foil section by name or id."""
        data = self.entity("FoilSection", id=id, name=name)
        return FoilSection(self._client, data)

    def analysis_2d(self, **params: Any) -> Analysis2D:
        """A configured 2D polar analysis over the visible foil sections.

        Pass any analysis parameters now or via ``set_parameters`` later::

            analysis = project.analysis_2d(alpha_range=[-10, 10],
                                           reynolds_million=1.0, flap_lock=True)
            result = analysis.run()        # raw numbers
            figures = analysis.figures()   # the web app's Plotly figures
        """
        return Analysis2D(self._client, **params)

    # ------------------------------------------------------------------ #
    # 2D optimization (OptiAeroFoil)

    def optimizations_2d(self) -> List[Optimization2D]:
        """High-level handles for every 2D optimization in the project."""
        return [Optimization2D(self._client, d) for d in self.entities("OptiAeroFoil")]

    def optimization_2d(
        self, name: Optional[str] = None, *, id: Optional[str] = None
    ) -> Optimization2D:
        """One 2D optimization by name or id."""
        data = self.entity("OptiAeroFoil", id=id, name=name)
        return Optimization2D(self._client, data)

    def create_optimization_2d(
        self, name: Optional[str] = None, **config: Any
    ) -> Optimization2D:
        """Create a 2D optimization entity; ``config`` as in ``Optimization2D.set_config``.

        The server assigns an initial name; pass ``name=`` to rename it.
        """
        data = self.create_entity("OptiAeroFoil", {})
        opt = Optimization2D(self._client, data)
        fields = dict(config)
        if name:
            fields["name"] = name
        if fields:
            result = opt.set_config(**fields)
            opt.name = result.get("name", opt.name)
        return opt

    def compute_polars(self, **params: Any) -> Dict[str, Any]:
        """Run the 2D polar analysis on all visible foil sections.

        Accepts the same parameters as the web app's polar plot, e.g.
        ``alpha_range=[-15, 15]``, ``reynolds_million=1.0``, ``ncrit=0.18``,
        ``mach=0.0``, ``solver=["NN"]``, ``fluid="water"``. Returns the raw
        payload, including ``plotly_graphics`` (Plotly figure JSON).

        For the numbers instead of ready-made figures, use :meth:`polar_data`.
        """
        return self._client.call("update_polar_plot", params)

    def polar_data(self, **params: Any) -> Dict[str, Any]:
        """Run the 2D polar analysis and return the raw data — you decide what to plot.

        Same parameters as :meth:`compute_polars`. Returns one entry per
        visible section with parallel arrays (one value per computed sweep
        point; unconverged points are ``None``). ``top_Cp``/``bot_Cp`` (with
        ``top_x``/``bot_x``) carry one array per sweep point — the chordwise
        pressure distribution::

            {"sections": [{"section": "naca0012", "n_points": 42,
                           "data": {"alpha": [...], "Cl": [...], "Cd": [...],
                                    "Cm": [...], "Cl_Cd": [...], "Re": [...], ...,
                                    "top_x": [[...], ...], "top_Cp": [[...], ...]}}],
             "variables": ["alpha", "Cl", "Cd", ...]}

        Example::

            result = project.polar_data(alpha_range=[-10, 10], reynolds_million=1.0)
            for s in result["sections"]:
                plt.plot(s["data"]["alpha"], s["data"]["Cl"], label=s["section"])
        """
        return self._client.call("get_polar_data", params)

    def optimize(
        self,
        entity_id: str,
        *,
        on_progress: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run a configured OptiAeroFoil optimization entity.

        Blocks until the optimization finishes; pass ``on_progress`` to
        stream progress and ``timeout=None`` to wait indefinitely.
        """
        return self._client.call(
            "run_optimization",
            entity_id=entity_id,
            on_progress=on_progress,
            timeout=timeout,
        )
