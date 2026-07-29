# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`pytakeoff` — synchronous Python client (SDK) for the Takeoff hydrofoil design platform. It speaks the **same WebSocket command protocol as the web frontend**, so every server command is reachable via `client.call("command_name", payload)`; the high-level classes are thin sugar over that. All permissions, credits, and rate limits are enforced server-side.

## Commands

```bash
pip install -e ".[dev]"        # editable install (a venv already exists at ./venv)
python -m pytest               # dev extra installs pytest, but there is no tests/ dir yet
python -m build                # sdist + wheel (what CI runs)
cd docs && make html           # Sphinx docs (needs pip install -e ".[docs]"); output docs/_build
```

- **Release:** bump `__version__` in `src/pytakeoff/__init__.py` (hatch reads the version from there), then cut a GitHub Release — `.github/workflows/publish.yml` builds and publishes to PyPI via Trusted Publishing (no tokens).
- **Commits:** never add AI co-author trailers or Claude attribution to commits/PRs.

## Architecture (src/pytakeoff/, ~1.5k lines)

Three layers; the flow of a call is: high-level method → `TakeoffClient.call()` → `WebSocketTransport.call()`.

**Auth & key resolution**
- `auth.py` — API-key-only auth: `POST /api/auth/api-token/` exchanges a `tk_<id>_<secret>` key for a ~1 h session token used on the WebSocket URL. Passwords appear only in the one-time interactive bootstrap (`TakeoffClient.setup()` → `create_api_key`) and are never stored.
- `keystore.py` — resolution order: `api_key=` arg → `TAKEOFF_API_KEY` env → `~/.takeoff/credentials` (JSON). The README's placeholder key (`tk_xxx…`) is deliberately treated as "no key" so unedited examples fall through instead of failing on the server.
- `__main__.py` — `python -m pytakeoff` (create+save key) / `python -m pytakeoff configure` (save existing key).

**Transport** (`transport.py` — the most intricate module; the wire protocol is documented in its module docstring)
- Frames: `{"event", "payload", "message_id"}`; responses correlate on `message_id` + `<command>_ack`. Non-matching frames are broadcasts → `on_event`.
- Long-running commands: immediate `accepted` ack → `status: "partial"` progress frames (→ `on_progress` callback) → final ack, all with the same `message_id`.
- A few mesh commands answer with a JSON envelope (`payload_type == "flatbuffer"`) plus one binary frame → returned undecoded as `FlatBufferResult`.
- A keepalive daemon thread pings/drains the socket between calls. It shares an `RLock` with `call()`: the lock is held for a whole command round-trip, and the keepalive only touches the socket when it can acquire it non-blocking. Preserve this invariant when touching transport code.

**High-level API**
- `client.py` — `TakeoffClient`: resilient `call()` — reconnects proactively when idle >30 s (`_STALE_AFTER`; a synchronous client can't answer server pings, so idle connections are dead anyway) and retries once after `ConnectionClosed` **only if** `exc.sent is False` (the frame provably never reached the server — mid-command drops are never retried). `commands()` lists all server commands live via REST. Default server `https://app.takeoff-technologies.com`; plain-http/dev URLs get port 8000 applied internally.
- `projects.py` — `ProjectsAPI` + `Project`: generic entity CRUD (`entity_type` like "FoilSection", "Wing", "OptiAeroFoil"; typed commands are snake_cased, e.g. `get_all_foil_section`) and factories for the handles below.
- `foil_sections.py` — `FoilSection`: three get/set pairs (control points / geometry / structure). Getters always fetch live from the server; setters are parametric B-spline refits, so they return *achieved* values that can differ from the request.
- `analysis.py` — `Analysis2D`: stateless on the server; holds params locally, sends the full set each `run()` (`get_polar_data`) or `figures()` (`update_polar_plot`, Plotly JSON).
- `optimizations.py` — `Optimization2D` over OptiAeroFoil entities. Constraints are translated between the GUI's flat table shape and the nested wire shape (`_geo_to_wire`/`_aero_to_wire`); keep both directions in sync when changing fields.
- `exceptions.py` — all under `TakeoffError`; server error codes map to `CommandError` subclasses in `transport._ERROR_CODE_CLASSES`: `rate_limited` → `RateLimited` (has `retry_after`), `queue_full` → `QueueFull`, `gui_session_active` → `GuiSessionActive`.

## Server-side constraints that shape the API

- **One session per user**, shared between scripts and the browser GUI. Entity edits from a script are allowed while the GUI is open; project switch/close commands raise `GuiSessionActive`.
- **Rate limits** on API-key connections: per-minute cap, tighter hourly cap on heavy commands (`run_simulation`/`run_optimization`), one heavy command in flight per account.

## Repo notes

- `pyproject.toml` restricts the sdist to an explicit allowlist so local/agent working files (`.claude`, `memory/`, scratch) can never leak into a release — keep new working directories out of that list.
- `examples/` is numbered in learning order (01–06 scripts, 07–09 notebooks) and referenced from the README; keep numbering consistent when adding.
- `docs/` is Sphinx (furo + myst-parser), published via `.readthedocs.yaml`.
