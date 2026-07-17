"""Step 3 — list your projects and see which one is open.

The server keeps one project session per user, shared with the web app:
if your browser has a project open, ``projects.current()`` returns it.

    python 03_projects.py
"""

from pytakeoff import TakeoffClient

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
        print("Open one with: project = client.projects.open(name)")
    else:
        print(f"\nCurrently open: {current.name}")
