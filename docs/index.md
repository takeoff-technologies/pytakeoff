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

## Generate a token

Scripts authenticate with an **API key** — a token shaped like `tk_<id>_<secret>` —
never with your password. Create one and save it in a single step:

```bash
python -m pytakeoff
```

This asks for your username and password **once**, creates the key over a single
request (the password is never stored), and saves it to `~/.takeoff/credentials`.

Already generated a key in the GUI (Account → **API Keys**)? Save that one instead:

```bash
python -m pytakeoff configure     # paste the key
```

Either way, your scripts need no key in the code from here on. Keys are managed and
revoked in the GUI; a leaked key can be revoked without touching your password or
your other keys.

## Quickstart

```python
from pytakeoff import TakeoffClient

with TakeoffClient() as client:                  # key read from your saved credentials
    for p in client.projects.list():
        print(p["name"])

    # the project your browser has open — or load one yourself if none is
    project = client.projects.current() or client.projects.open("my_foil")

    section = project.foil_sections()[0]
    print(section.geometry())                    # tc / camber / LE radius / ...

    result = project.analysis_2d(alpha_range=[-5, 0, 5, 10],
                                 reynolds_million=1.0).run()
```

New here? Start with {doc}`getting-started`, then browse the {doc}`guide` for each
workflow. Ready-to-run scripts and notebooks are in {doc}`examples/index`, and the
complete {doc}`api` is generated from the source.

```{toctree}
:maxdepth: 2
:hidden:

getting-started
guide
examples/index
api
```
