# Guide

`pytakeoff` works on the project currently open in your session — the same session
the web app uses. Get a handle to that project, then work with its **foil sections**,
run **2D analyses**, and drive **2D optimizations**. Every getter reads live values,
so a script and the browser always see the same state.

## Projects

```python
project = client.projects.current()           # the project open in your session, or None
project = client.projects.open("my_foil")      # load one by name and make it current
project = client.projects.open(id="…")         # ...or by project_id (from projects.list())
project = client.projects.create("draft")      # new project, made current
project.save()                                 # persist (clears the unsaved-changes flag)
```

The server keeps **one session per user**, shared with the web app. `current()`
returns the project your browser has open, or `None` when nothing is open. A script
running on its own sets the current project itself:

```python
project = client.projects.current() or client.projects.open("my_foil")
```

`projects.list()` returns every project (`name`, `project_id`, timestamps). While a
browser session is open on the same account, switching projects from a script is
refused ({class}`~pytakeoff.GuiSessionActive`) because the two share one project —
work on `current()` instead, or close the browser.

---

## Foil sections

A {class}`~pytakeoff.FoilSection` has three groups of state, each with a **live
getter** and a **parametric setter**:

| Group | Getter | Setter | What it is |
| --- | --- | --- | --- |
| Control points | `control_points()` | `set_control_points()` | the B-spline that *is* the shape |
| Geometric | `geometry()` | `set_geometry()` | thickness, camber, LE radius, TE thickness/angle |
| Structural | `structure()` | `set_structure()` | area, Ixx, section modulus, torsion constant |

Getters always fetch live values from the server. Setters send the change and return
the **resulting** values — the parametric setters refit the B-spline, so the achieved
value can differ marginally from the one you asked for. **Always trust the returned
dict, not your input.**

### Getting handles

```python
sections = project.foil_sections()            # every section -> list[FoilSection]
section  = project.foil_section("main_foil")  # one by name
section  = project.foil_section(id="e7213a74-…")   # or by id

section.id      # 'e7213a74-…'
section.name    # 'main_foil'
```

### Control points — the shape itself

`control_points()` returns the B-spline control net:

```python
cp = section.control_points()
# {"upper": [[x, y], …], "lower": [[x, y], …], "degree": 4, "n_coefs": 8}
```

`upper`/`lower` are control-point lists — **not** the drawn outline (that's
`points()`). `set_control_points()` replaces either side and rebuilds, returning the
stored net:

```python
section.set_control_points(upper=new_upper, lower=new_lower)
section.set_control_points(lower=new_lower)   # change one side only
```

Because the control points define the geometry exactly, capturing them and setting
them back is a **lossless restore** — the idiom for "try an edit, then undo it":

```python
cp = section.control_points()                       # snapshot
section.set_geometry(tc=section.geometry()["tc"] * 1.2)   # experiment (20% thicker)
section.set_control_points(upper=cp["upper"], lower=cp["lower"])   # exact restore
```

Work one point at a time when you only need to nudge a single node:

```python
n = section.n_control_points()             # points per side (upper and lower match)
p = section.control_point(2, "upper")      # [x, y] at index 2 on the upper side
section.set_control_point(2, [p[0], p[1] + 0.01], "upper")   # move it and rebuild
```

### Geometric parameters

`geometry()` returns the parametric descriptors, in **GUI units** — `tc`, `camber`
and `te_thickness` are percent of chord:

```python
section.geometry()
# {"tc": 12.0, "camber": 2.5, "le_radius": 0.62, "te_thickness": 0.25, "te_angle": 0.0}
```

`set_geometry()` sets any subset and refits the B-spline. Omitted parameters are left
to the refit; the returned dict holds the achieved values:

```python
achieved = section.set_geometry(tc=12.0, camber=2.5)
print(achieved["tc"])     # e.g. 11.998 — refit lands close, not exact
```

### Structural parameters

`structure()` returns section properties. `centroid` is read-only (computed); the
others can be driven parametrically:

```python
section.structure()
# {"area": 0.087, "Ixx": 9.3e-5, "SMx": 1.35e-3, "J": 3.7e-4, "centroid": [0.33, -2e-4]}

section.set_structure(area=section.structure()["area"] * 1.1)   # 10% more area
```

Setting a structural target reshapes the section to hit it (same refit caveat as
`set_geometry`).

### The outline

`points()` returns the **computed outline** — the drawn curve, distinct from the
control net:

```python
xy = section.points()     # [[x, y], …]
```

### Putting it together

```python
import matplotlib.pyplot as plt

section = project.foil_sections()[0]
cp = section.control_points()

# outline + control net
plt.figure(figsize=(9, 3))
plt.plot(*zip(*section.points()), "-", label="outline")
plt.plot(*zip(*cp["upper"]), "o--", label="upper control points")
plt.plot(*zip(*cp["lower"]), "s--", label="lower control points")
plt.axis("equal"); plt.legend(); plt.title(section.name); plt.show()

# make it 20% thicker, compare, then restore exactly
before = section.points()
section.set_geometry(tc=section.geometry()["tc"] * 1.2)
after = section.points()
section.set_control_points(upper=cp["upper"], lower=cp["lower"])
```

---

## 2D analysis

`project.analysis_2d(**params)` builds an {class}`~pytakeoff.Analysis2D` that holds
your sweep parameters locally. The analysis is **stateless on the server** — every
`run()` sends the full parameter set — and the sweep runs over **every visible foil
section** in the project.

### Parameters

| Parameter | Default | Meaning |
| --- | --- | --- |
| `alpha_range` | `[-15, -5, 0, 5, 15]` | angles of attack, degrees |
| `reynolds_million` | `1` | Reynolds number, in millions |
| `flap_range` | `[-15, -5, 0, 5, 15]` | flap angles swept **per alpha** |
| `flap_lock` | `False` | `True` = plain alpha sweep (no flap sweep) |
| `ncrit` | `0.18` | transition criterion (0.18 water, ~9 air) |
| `mach` | `0.0` | Mach number |
| `solver` | `["NN"]` | also `"XFOIL"`, `"IA"`, … |
| `xtr_upper` / `xtr_lower` | `1.0` | forced transition locations (x/c) |
| `fluid` | `"water"` | fluid medium |
| `elevation` | `0` | elevation |

Set parameters at construction or later. Unknown names raise `ValueError` (typo
protection); passing `None` removes a parameter so the server default applies:

```python
a = project.analysis_2d(alpha_range=[-10, 10], reynolds_million=1.0)
a.set_parameters(flap_lock=True, solver=["NN"])
a.parameters()      # the current set that will be sent
```

:::{note}
By default `flap_range` sweeps a **set of flap angles at each alpha** — you get a grid
of points, not a single curve. For a plain alpha sweep, set `flap_lock=True`.
:::

### `run()` — the raw numbers

```python
result = a.run()
```

```python
{
  "sections": [
    {"section": "foil_section_1", "n_points": 42,
     "data": {
        "alpha": [...], "Cl": [...], "Cd": [...], "Cm": [...], "Cl_Cd": [...],
        "Re": [...], ...,                       # ~two dozen scalars per point
        "top_x": [[...], ...], "top_Cp": [[...], ...],   # chordwise, one array per point
        "bot_x": [[...], ...], "bot_Cp": [[...], ...],
     }}
  ],
  "variables": ["alpha", "Cl", "Cd", ...]
}
```

- **One entry per visible section.**
- Scalar arrays are **parallel** — one value per computed sweep point. Unconverged
  points are `None`; filter them before plotting or reducing.
- `variables` lists every scalar output per point: `alpha`, `Cl`, `Cd`, `Cdp`, `Cdf`,
  `Cm`, `Cl_Cd`, `top_xtr`/`bot_xtr`, `flap_angle`, `Re`, `mach`, `Ca`, `Cp_Ca`,
  `Cp_max`/`Cp_min`, `Cpx_max`/`Cpx_min`, `CoPx`/`CoPy`, `Vinception`/`Vinception_kts`.
- **Chordwise pressure:** `top_Cp`/`bot_Cp` are lists of arrays — one Cp distribution
  per sweep point — paired with `top_x`/`bot_x`.

```python
# best glide per section, skipping unconverged points
for s in result["sections"]:
    d = s["data"]
    rows = [(a_, cl, cd, g) for a_, cl, cd, g in
            zip(d["alpha"], d["Cl"], d["Cd"], d["Cl_Cd"]) if cl is not None]
    a_, cl, cd, g = max(rows, key=lambda r: r[3])
    print(f"{s['section']}: best Cl/Cd={g:.1f} at alpha={a_:.0f}")

# chordwise Cp of the last sweep point of the first section
d = result["sections"][0]["data"]
i = len(d["alpha"]) - 1
plt.plot(d["top_x"][i], d["top_Cp"][i], label="upper")
plt.plot(d["bot_x"][i], d["bot_Cp"][i], label="lower")
plt.gca().invert_yaxis(); plt.legend(); plt.show()
```

### `figures()` — ready-made Plotly

When you want the web app's exact plots instead of raw arrays:

```python
figs = a.figures()                 # list of Plotly figure dicts
figs = a.figures(dark_mode=True)   # plot-only options also accepted
```

---

## 2D optimization

An {class}`~pytakeoff.Optimization2D` wraps an OptiAeroFoil entity — a full
airfoil-shape optimization with objectives, constraints, and a history of stored
runs.

### List, create, or fetch

```python
opts = project.optimizations_2d()          # list ALL optimizations -> [Optimization2D, ...]
opt  = project.optimization_2d("my_opt")   # fetch an existing one, by name (or id="…")
opt  = project.create_optimization_2d("my_opt", initial_section="main_foil",
                                       solver="NN", optimizer_config={"maxiter": 100, "tol": 1e-3})

for o in project.optimizations_2d():       # e.g. inspect them
    print(o.name, o.config()["converged"])
```

### Configure (modify an existing one)

Fetch an optimization, then change any part of it — `set_config(**fields)` sets any
definition field (including `name` to rename); `config()` returns the whole
definition (including the run history):

| Field | Example | Meaning |
| --- | --- | --- |
| `initial_section` | `"main_foil"` | the shape to optimize from |
| `ref_section` | `"main_foil"` | reference for `"ref"`-valued constraints |
| `solver` | `"NN"` | polar solver used during the search |
| `max_iterations` / `optimizer_config` | `{"maxiter": 100, "tol": 1e-3}` | optimizer budget |
| `bounds` | `0.03` | how far control points may move |
| `te_thickness` / `te_mode` | `0.001` / `"tc"` | trailing-edge handling |
| `optimize_flap` (+ flap bounds) | `True` | let a flap deflect during the search |
| `fluid` / `elevation` | `"water"` / `0` | flow environment |

### Objectives (up to 3)

A weighted set of goals, each evaluated at a flow condition:

```python
opt.set_objectives([
    {"func": "maxGlide", "Re": 1e6, "alpha": 4.0, "solve_for": "fixed", "weight": 1.0},
])
opt.objectives()   # read them back
```

- **`func`** — `"minCd"`, `"maxCl"`, `"maxGlide"`, or any `min<var>`/`max<var>` over
  the polar variables.
- **`solve_for`** — `"fixed"` (evaluate at `alpha`), `"alpha"` (float alpha to hit
  `target_Cl`), or `"flap"`.
- **condition fields** — `Re`, `Vs`, `alpha`, `flap_angle`, `Ncrit`, `target_Cl`,
  plus `alpha_robust_range` / `flap_robust_range` / `Ncrit_robust_range` for robust
  optimization over a band of conditions.

### Constraints

Same fields as the GUI tables — geometric and aerodynamic:

```python
opt.set_constraints(
    geo=[{"variable": "get_tc", "operator": ">", "value": 0.10}],
    aero=[{"variable": "Cd", "operator": "<", "value": "ref",
           "Re": 1e6, "alpha": 8.0, "solve_for": "fixed"}],
)
opt.constraints()   # {"geo": [...], "aero": [...]}
```

- **geo variables** — `area`, `SMx`, `Ixx`, `J`, `get_tc`, `get_max_camber`, …
- **aero variables** — any polar variable, evaluated at the given flow condition.
- **`operator`** — `">"`, `"<"`, `"=="`. **`value`** — a number, or `"ref"` to
  compare against `ref_section`.

### Run

```python
response = opt.run(
    on_progress=lambda pct, msg: print(f"{pct:5.1f}%  {msg or ''}"),
    timeout=None,      # wait as long as it takes
)
# {"success": True, "optimized_section_name": "OptSection", ...}
```

`run()` blocks until the optimization finishes and streams progress through
`on_progress`.

### Inspect results

```python
opt.runs()              # ["1", "2", …] — stored run keys, in order
r = opt.result()        # the latest run (pass a run key for a specific one)
# {"objectives", "bounds", "opt_data", "opt_section", "run_number"}

score = r["opt_data"]["score"]           # overall objective score
obj1  = r["opt_data"]["objective_1"]     # {"Cl": …, "Cd": …, …} at its design point
geom  = r["opt_section"]                  # the optimized geometry
```

### Save, restore, clean up

```python
saved = opt.save_result()                        # optimized section -> project as a FoilSection
optimized = project.foil_section(id=saved["section_id"])

opt.restore("1")                                 # load a stored run back as working state
opt.delete_runs(["1"])                           # drop stored runs by key
```

### Full example

```python
section = project.foil_sections()[0]

opt = project.create_optimization_2d(
    "demo", initial_section=section.name, solver="NN",
    optimizer_config={"maxiter": 20, "tol": 1e-3},
)
opt.set_objectives([{"func": "maxGlide", "Re": 1e6, "alpha": 4.0, "solve_for": "fixed"}])
opt.set_constraints(geo=[{"variable": "get_tc", "operator": ">", "value": 0.10}])

opt.run(on_progress=lambda pct, msg: print(f"{pct:5.1f}%  {msg or ''}"), timeout=None)

r = opt.result()
obj = r["opt_data"]["objective_1"]
print(f"Cl={obj['Cl']:.4f}  Cd={obj['Cd']:.6f}  glide={obj['Cl']/obj['Cd']:.1f}")

saved = opt.save_result()
optimized = project.foil_section(id=saved["section_id"])
plt.plot(*zip(*section.points()), label=f"original ({section.name})")
plt.plot(*zip(*optimized.points()), label=f"optimized ({optimized.name})")
plt.axis("equal"); plt.legend(); plt.show()
```

---

## Errors worth catching

The high-level calls above can raise these — handle the ones your workflow cares
about:

```python
import time
from pytakeoff import RateLimited, GuiSessionActive, CommandError, CommandTimeout

try:
    opt.run(timeout=3600)
except RateLimited as e:
    time.sleep(e.retry_after)      # wait the server-suggested interval, then retry
except GuiSessionActive:
    ...                             # close your browser session to switch/close projects
except CommandTimeout:
    ...                             # took longer than the timeout
except CommandError as e:
    print(e, e.payload)             # server rejected the command; payload has details
```
