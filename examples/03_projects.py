"""Step 3 — list your projects and see which one is open.

The server keeps one project session per user, shared with the web app:
if your browser has a project open, ``projects.current()`` returns it.

    python 03_projects.py
"""

from pytakeoff import TakeoffClient

API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # get a key in the GUI (Account -> API Keys) or run: python -m pytakeoff

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
