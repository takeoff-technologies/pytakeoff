"""Step 1 - get an API key and save it (run once).

pytakeoff authenticates with an API key, never with your password. The
easiest setup is from the terminal:

    python -m pytakeoff              # create a NEW key and save it
    python -m pytakeoff configure    # save a key you already made in the GUI

Both write ~/.takeoff/credentials, so afterwards your scripts just do:

    from pytakeoff import TakeoffClient
    with TakeoffClient() as client:      # no key in the code
        ...

Running this file does the same as `python -m pytakeoff`: it asks for your
username/password once (never stored), creates a key, and saves it.
"""

from pytakeoff import TakeoffClient

if __name__ == "__main__":
    TakeoffClient.setup()
