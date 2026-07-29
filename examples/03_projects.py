"""Step 3 — list your projects, open one, and close it again.

The server keeps one project session per user, shared with the web app:
if your browser has a project open, ``projects.current()`` returns it.

Because the two share one project, ``open``/``create``/``close``/``delete`` are
refused while a browser session is live — pass ``force=True`` to take it over.

    python 03_projects.py
"""

from pytakeoff import TakeoffClient
from pytakeoff.exceptions import GuiSessionActive

# Ran `python -m pytakeoff`? Leave this line exactly as it is: the all-x
# placeholder counts as no key, so your saved credentials (or the
# TAKEOFF_API_KEY env var) are used automatically.
# Otherwise, paste your own key here - GUI: Account -> API Keys.
API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

with TakeoffClient(api_key=API_KEY) as client:
    projects = client.projects.list()
    print(f"{len(projects)} project(s):")
    for p in projects:
        print(f"  - {p['name']:<30} updated {p.get('updated_at', '?')}")

    current = client.projects.current()
    if current is None:
        print("\nNo project is open in your session right now.")
    else:
        print(f"\nCurrently open: {current.name}")

    if not projects:
        raise SystemExit("Create a project in the web app first.")

    # Open one and make it current. While the web app is open on the same
    # account this raises GuiSessionActive - force=True takes the session over
    # and tells the browser to reload.
    name = projects[0]["name"]
    try:
        project = client.projects.open(name)
    except GuiSessionActive:
        print(f"\nA browser session is open - taking it over to load {name!r}")
        project = client.projects.open(name, force=True)

    print(f"Opened: {project.name}")
    print(f"  {len(project.foil_sections())} foil section(s)")

    # Leave the session with nothing open. The next connection auto-loads your
    # most recent project, so this is per-session, not permanent.
    client.projects.close(force=True)
    print(f"Closed. current() is now {client.projects.current()}")
