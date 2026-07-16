# Getting started

## Install

```bash
pip install pytakeoff
```

`pytakeoff` needs only `requests` and `websocket-client`; both come as dependencies.

## Get an API key (token)

Scripts authenticate with an **API key** — a token shaped like
`tk_<id>_<secret>` — never with your password. Get one two ways:

**A. From the GUI**

Account → **API Keys** → *Generate API key*. The key is shown **once** — copy it.

**B. From the terminal**

```bash
python -m pytakeoff
```

This asks for your username and password **once**, creates a key over a single
request (the password is never stored), and saves it (see below).

Manage or revoke keys anytime in the GUI under Account → API Keys. A leaked key
can be revoked without affecting your password or other keys.

## Save it once — no key in your code

Rather than pasting the key into every script, save it once so `TakeoffClient()`
picks it up automatically:

```bash
python -m pytakeoff             # create a NEW key and save it
python -m pytakeoff configure   # save a key you ALREADY made in the GUI (paste it)
```

From then on, no key in your code:

```python
from pytakeoff import TakeoffClient

with TakeoffClient() as client:          # key read from your saved credentials
    print(client.username)
```

You can also save a key from Python — handy right after generating one in the GUI:

```python
from pytakeoff import TakeoffClient
TakeoffClient.configure(api_key="tk_…")
```

:::{warning}
Your saved credentials (`~/.takeoff/credentials`) hold a real key — **keep the
file private and never commit it**, and never put a key inside a project
directory. Leaked a key? Revoke it in the GUI; your password and other keys are
unaffected.
:::

### Resolution order

`TakeoffClient` resolves the key, in order, from:

1. the `api_key=` argument,
2. the `TAKEOFF_API_KEY` environment variable (recommended for CI),
3. your saved credentials.

An empty value or the documentation placeholder (`tk_xxxx...`) is treated as *not
provided*, so an unedited example falls through to the environment variable or
saved credentials instead of failing.

## Connect

```python
from pytakeoff import TakeoffClient

with TakeoffClient() as client:
    print(f"Connected as {client.username}")
    print(f"{len(client.projects.list())} project(s)")
```

The context manager closes the connection for you. `TakeoffClient` connects on
construction by default; pass `auto_connect=False` to defer, then call
{meth}`~pytakeoff.TakeoffClient.connect`.

## First workflow

```python
with TakeoffClient() as client:
    project = client.projects.current()          # whatever the web app has open
    if project is None:                          # nothing open? set one yourself:
        project = client.projects.open("my_project")
    section = project.foil_sections()[0]

    print(section.geometry())                    # tc / camber / LE radius / ...
    section.set_geometry(tc=section.geometry()["tc"] * 1.05)   # 5% thicker

    result = project.analysis_2d(alpha_range=[-5, 0, 5, 10],
                                 reynolds_million=1.0, flap_lock=True).run()
    for s in result["sections"]:
        print(s["section"], "->", s["n_points"], "points")
```

`projects.current()` returns the project your browser has open, or `None` if
nothing is open. Running a script on its own? Set the current project with
`projects.open("name")` (or `open(id=...)`) — no web app needed. See the
{doc}`guide` for foil sections, 2D analysis, and 2D optimization.
