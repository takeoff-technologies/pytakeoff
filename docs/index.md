# pytakeoff

Python client for the [Takeoff](https://github.com/takeoff-technologies) hydrofoil
design platform.

Everything the web app can do — projects, foil sections, analysis, optimization —
scripted from Python. `pytakeoff` speaks the same WebSocket command protocol as the
frontend, so every server command is available, and all permissions, credits, and
rate limits are enforced server-side exactly as in the browser.

## Install

```bash
pip install pytakeoff
```

## Quickstart

```python
from pytakeoff import TakeoffClient

# Save your API key once, then no key in your code (see Getting started):
#     python -m pytakeoff
with TakeoffClient() as client:
    for p in client.projects.list():
        print(p["name"])

    project = client.projects.current()
    section = project.foil_sections()[0]
    print(section.geometry())

    result = project.analysis_2d(alpha_range=[-5, 0, 5, 10],
                                 reynolds_million=1.0).run()
```

New here? Start with {doc}`getting-started`, then browse the {doc}`guide` for each
workflow. The complete {doc}`api` is generated from the source.

```{toctree}
:maxdepth: 2
:hidden:

getting-started
guide
api
```
