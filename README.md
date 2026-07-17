# pytakeoff

Python client for the [Takeoff](https://github.com/takeoff-technologies) hydrofoil design platform.

Everything the web app can do — projects, foil sections, analysis, optimization — scripted from Python. `pytakeoff` speaks the same WebSocket command protocol as the frontend, so every server command is available, and all permissions, credits, and rate limits are enforced server-side exactly as in the browser.

## Install

```bash
pip install pytakeoff
```

## Authentication — API keys, never passwords

Scripts authenticate with an **API key** — a token shaped like
`tk_<id>_<secret>`, never your password. Get one either way:

- **In the GUI:** Account → API Keys → Generate API key (shown once — copy it).
- **From the terminal (one-time interactive setup):**

  ```bash
  python -m pytakeoff             # create a NEW key (asks for your password) and save it
  python -m pytakeoff configure   # save a key you ALREADY made in the GUI (paste it)
  ```

  The first form asks for your username/password **once**, creates a key over a
  single request, and saves it to `~/.takeoff/credentials`. The password is
  never stored.

Once saved, no key in your code — `TakeoffClient()` picks it up:

```python
from pytakeoff import TakeoffClient

with TakeoffClient() as client:          # key read from your saved credentials
    print(client.username)
```

`TakeoffClient` resolves the key, in order, from the `api_key=` argument, the
`TAKEOFF_API_KEY` environment variable (recommended for CI), or your saved
`~/.takeoff/credentials` file. **Never commit a key to a repository.** Leaked a
key? Revoke it in the GUI; your password and other keys are unaffected.

## Quickstart

```python
from pytakeoff import TakeoffClient

# Your API key (GUI → Account → API Keys). Or omit api_key= entirely and it is
# resolved from TAKEOFF_API_KEY / ~/.takeoff/credentials. Never commit a real key.
API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Connects to the official https://app.takeoff-technologies.com by default —
# no port needed. Self-hosted / dev: TakeoffClient("http://localhost", api_key=...)
# (plain-http URLs get port 8000 applied internally).
with TakeoffClient(api_key=API_KEY) as client:
    # Projects
    for p in client.projects.list():
        print(p["name"])

    project = client.projects.open("my_foil")

    # Entities (FoilSection, Wing, Bulb, Hull, Sail, ...)
    sections = project.foil_sections()
    project.update_entity("FoilSection", {"id": "<section-id>", "name": "renamed"})

    # 2D polar analysis (returns Plotly figure JSON among other data)
    polars = project.compute_polars(alpha_range=[-10, 10], reynolds_million=1.0)

    # Optimization with live progress
    result = project.optimize(
        "<optiaerofoil-entity-id>",
        on_progress=lambda pct, msg: print(f"{pct}% {msg or ''}"),
        timeout=None,  # wait as long as it takes
    )

    project.save()
```

## Examples — simplest to more complex

Runnable scripts in [`examples/`](examples/), numbered in learning order:

1. [`01_create_api_key.py`](examples/01_create_api_key.py) — one-time setup: create an API key from the terminal (or use the GUI) and copy it into your scripts.
2. [`02_connect.py`](examples/02_connect.py) — connect and print who you are.
3. [`03_projects.py`](examples/03_projects.py) — list your projects and show the currently open one (`client.projects.current()`).
4. [`04_foil_section.py`](examples/04_foil_section.py) — the high-level `FoilSection` API: get/set control points, geometric parameters, structural parameters.
5. [`05_polar_analysis.py`](examples/05_polar_analysis.py) — 2D analysis: configure a sweep, run it, work with the raw numbers (incl. chordwise Cp).
6. [`06_optimization.py`](examples/06_optimization.py) — 2D optimization: configure objectives/constraints, run with progress, inspect the result.

Prefer notebooks? The same three topics with plots: [`07_foil_section.ipynb`](examples/07_foil_section.ipynb), [`08_analysis_2d.ipynb`](examples/08_analysis_2d.ipynb), [`09_optimization_2d.ipynb`](examples/09_optimization_2d.ipynb).

## Foil sections

`project.foil_sections()` / `project.foil_section(name)` return high-level handles with three get/set pairs. Getters fetch live values; setters apply the change and return the achieved values (parametric setters refit the B-spline, so they can differ marginally from the request). Units match the GUI: `tc`, `camber`, `te_thickness` are percent of chord.

```python
section = project.foil_section("main_foil")

cp = section.control_points()      # {"upper": [[x,y],...], "lower": [...], "degree", "n_coefs"}
section.set_control_points(upper=cp["upper"], lower=cp["lower"])

geo = section.geometry()           # {"tc", "camber", "le_radius", "te_thickness", "te_angle"}
section.set_geometry(tc=12.0, camber=2.5)

struct = section.structure()       # {"area", "Ixx", "SMx", "J", "centroid"(read-only)}
section.set_structure(area=struct["area"] * 1.1)

xy = section.points()              # the computed outline coordinates
```

## 2D analysis

`project.analysis_2d(...)` holds sweep parameters (`alpha_range`, `reynolds_million`, `flap_range`/`flap_lock`, `ncrit`, `mach`, `solver`, `fluid`, ...) and runs them over the visible foil sections:

```python
analysis = project.analysis_2d(alpha_range=[-10, 10], reynolds_million=1.0, flap_lock=True)
result = analysis.run()       # raw arrays: alpha, Cl, Cd, Cm, Cl_Cd, ..., top_x/top_Cp (chordwise)
figures = analysis.figures()  # or the web app's ready-made Plotly figures
```

## 2D optimization

`project.create_optimization_2d(...)` / `project.optimization_2d(name)` return an `Optimization2D` handle on an OptiAeroFoil entity:

```python
opt = project.create_optimization_2d("my_opt", initial_section="main_foil", solver="NN",
                                     optimizer_config={"maxiter": 100, "tol": 1e-3})
opt.set_objectives([{"func": "maxGlide", "Re": 1e6, "alpha": 4.0, "solve_for": "fixed"}])
opt.set_constraints(geo=[{"variable": "get_tc", "operator": ">", "value": 0.10}])

response = opt.run(on_progress=lambda pct, msg: print(pct, msg), timeout=None)

r = opt.result()              # latest run: opt_data (scores), opt_section (geometry)
opt.save_result()             # optimized section -> project as a FoilSection
opt.restore("1")              # reload a stored run; opt.runs(), opt.delete_runs([...])
```

Objective `func` is `"minCd"`, `"maxCl"`, `"maxGlide"`, or any `min<var>`/`max<var>` over the polar variables; `solve_for` is `"fixed"`, `"alpha"` (hit `target_Cl`), or `"flap"`.

## Error handling

```python
import time
from pytakeoff import (
    CommandError, CommandTimeout, ConnectionClosed, GuiSessionActive, RateLimited,
)

try:
    opt.run(timeout=3600)                         # any high-level call can raise these
except RateLimited as e:
    time.sleep(e.retry_after)                 # server throttled us; wait and retry
except GuiSessionActive:
    print("Close your browser session to switch projects from a script")
except CommandError as e:
    print("Server rejected:", e, e.payload)   # payload carries structured details
except CommandTimeout:
    print("Took too long")
except ConnectionClosed:
    client.reconnect()                        # re-exchanges the API key if needed
```

## Good to know

- **Scripts are rate limited.** API-key connections have per-account command budgets (a per-minute cap, plus a tighter hourly cap on heavy commands like `run_simulation`/`run_optimization`), one heavy command in flight at a time, and a small cap on concurrent connections. Limits scale with your plan. The browser GUI is not affected. Hitting a limit raises `RateLimited` with `retry_after`.
- **One session per user.** The server keeps a single session per account, shared between your scripts and your browser. While your GUI is open, entity edits from a script are allowed (the GUI shows a "Script connected" chip and can refresh), but project switching/closing commands raise `GuiSessionActive`.
- **Credits & permissions** apply exactly as in the web app; paid commands bill your account.
- **Binary mesh data:** a few commands (`get_entity_mesh`, `get_simulation_visualization`, ...) answer with raw FlatBuffer bytes. `pytakeoff` returns them as a `FlatBufferResult` without decoding — most scripting workflows never need them.
- **Long sessions:** session tokens expire after ~1 hour; if the connection drops, `client.reconnect()` re-exchanges your API key and reconnects.

## Development

```bash
git clone https://github.com/takeoff-technologies/pytakeoff.git
cd pytakeoff
pip install -e ".[dev]"
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
