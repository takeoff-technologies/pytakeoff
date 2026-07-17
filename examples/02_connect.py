"""Step 2 — connect to the server.

    python 02_connect.py
"""

from pytakeoff import TakeoffClient

# Ran `python -m pytakeoff`? Leave this line exactly as it is: the all-x
# placeholder counts as no key, so your saved credentials (or the
# TAKEOFF_API_KEY env var) are used automatically.
# Otherwise, paste your own key here - GUI: Account -> API Keys.
API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

with TakeoffClient(api_key=API_KEY) as client:
    print(f"Connected to {client.base_url} as {client.username}")
