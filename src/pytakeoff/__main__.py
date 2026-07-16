"""Command-line entry point for one-time credential setup.

    python -m pytakeoff              create a new API key (asks for your
                                     password) and save it to ~/.takeoff/credentials
    python -m pytakeoff configure    save a key you already made in the GUI
"""

from __future__ import annotations

import sys

from .client import TakeoffClient


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0].lower() if args else "setup"
    try:
        if cmd in ("configure", "config"):
            TakeoffClient.configure()
        elif cmd in ("setup", ""):
            TakeoffClient.setup()
        else:
            print(__doc__)
            return 2
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
