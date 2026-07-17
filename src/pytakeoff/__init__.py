"""pytakeoff — Python client for the Takeoff hydrofoil design platform.

One-time setup — create an API key and save it to ``~/.takeoff/credentials``::

    python -m pytakeoff              # create a new key (asks for your password)
    python -m pytakeoff configure    # save a key you already made in the GUI

After that, scripts connect with no key in the code::

    from pytakeoff import TakeoffClient

    with TakeoffClient() as client:        # key read from ~/.takeoff/credentials
        for p in client.projects.list():
            print(p["name"])

Authentication is by API key only, resolved from the ``api_key=`` argument, the
``TAKEOFF_API_KEY`` env var, or the ``~/.takeoff/credentials`` file (in that
order). Keys are created/managed in the GUI under Account → API Keys.
"""

from .client import TakeoffClient
from .exceptions import (
    AuthenticationError,
    CommandError,
    CommandTimeout,
    ConnectionClosed,
    GuiSessionActive,
    NotConnectedError,
    QueueFull,
    RateLimited,
    TakeoffError,
)
from .analysis import Analysis2D
from .foil_sections import FoilSection
from .optimizations import Optimization2D
from .projects import Project, ProjectsAPI
from .transport import FlatBufferResult

__version__ = "0.1.1"

__all__ = [
    "TakeoffClient",
    "Project",
    "ProjectsAPI",
    "FoilSection",
    "Analysis2D",
    "Optimization2D",
    "FlatBufferResult",
    "TakeoffError",
    "AuthenticationError",
    "CommandError",
    "CommandTimeout",
    "ConnectionClosed",
    "GuiSessionActive",
    "NotConnectedError",
    "QueueFull",
    "RateLimited",
    "__version__",
]
