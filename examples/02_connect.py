"""Step 2 — connect to the server.

    python 02_connect.py
"""

from pytakeoff import TakeoffClient

API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # get a key in the GUI (Account -> API Keys) or run: python -m pytakeoff

with TakeoffClient(api_key=API_KEY) as client:
    print(f"Connected to {client.base_url} as {client.username}")
