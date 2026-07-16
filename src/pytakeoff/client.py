"""High-level client for the Takeoff platform."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import requests

from . import keystore
from .auth import AuthSession, Credentials
from .exceptions import AuthenticationError, ConnectionClosed, NotConnectedError
from .projects import ProjectsAPI
from .transport import ProgressCallback, WebSocketTransport

logger = logging.getLogger("pytakeoff")

_UNSET = object()

EventHandler = Callable[[Dict[str, Any]], None]

# Official Takeoff server — the port is never part of the public URL.
_DEFAULT_BASE_URL = "https://app.takeoff-technologies.com"

# Reconnect proactively when the socket has been idle this long. The server
# pings every ~20 s and drops clients that miss a pong for ~20 s more; a
# synchronous client that is idle between calls can never answer, so any
# connection idle past the first ping is on death row anyway.
_STALE_AFTER = 30.0
# Internal default for plain-http (local/dev) servers when no port is given.
_DEFAULT_DEV_PORT = 8000


def _normalize_base_url(base_url: str) -> str:
    """Apply the port policy to a server URL.

    - A port already present in the URL is kept.
    - Otherwise: https URLs stay portless (443 implied — the official server
      never publishes a port), while plain-http URLs (local/dev servers) get
      the internal default :data:`_DEFAULT_DEV_PORT`.

    Bare hosts without a scheme are accepted: localhost-style hosts default
    to http (dev), anything else to https.
    """
    url = base_url.strip().rstrip("/")
    if "://" not in url:
        host = url.split("/", 1)[0].split(":", 1)[0]
        scheme = "http" if host in ("localhost", "127.0.0.1") else "https"
        url = f"{scheme}://{url}"
    parts = urlsplit(url)
    netloc = parts.netloc
    if parts.port is None and parts.scheme == "http":
        netloc = f"{netloc}:{_DEFAULT_DEV_PORT}"
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def _derive_ws_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/ws/dcomm/", "", ""))


class TakeoffClient:
    """Synchronous client for the Takeoff platform.

    Authentication is by **API key only**. Save a key once with
    ``python -m pytakeoff`` (or :meth:`setup` / :meth:`configure`), then::

        from pytakeoff import TakeoffClient

        with TakeoffClient() as client:            # key read from your credentials
            project = client.projects.open("my_foil")
            sections = project.foil_sections()
            project.save()

    The key is resolved from the ``api_key=`` argument, the
    ``TAKEOFF_API_KEY`` environment variable, or ``~/.takeoff/credentials``
    (written by :meth:`setup` / :meth:`configure`), in that order.

    Notes on server-side behaviour for script connections:

    - Commands are **rate limited** per account (:class:`pytakeoff.RateLimited`
      carries ``retry_after`` seconds when you hit a limit).
    - The server keeps one project session per user. While your browser is
      connected with the same account, project switching/closing commands are
      rejected (:class:`pytakeoff.GuiSessionActive`); entity edits are allowed
      and appear live in the GUI, which shows a "Script connected" chip.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        timeout: float = 120.0,
        auto_connect: bool = True,
    ) -> None:
        resolved_url = keystore.resolve_base_url(base_url) or _DEFAULT_BASE_URL
        self.base_url = _normalize_base_url(resolved_url)
        self.timeout = timeout
        self._api_key = keystore.resolve_api_key(api_key)
        self._auth = AuthSession(self.base_url)
        self._credentials: Optional[Credentials] = None
        self._transport = WebSocketTransport(_derive_ws_url(self.base_url), timeout=timeout)
        self._transport.on_event = self._handle_event
        self._event_handlers: Dict[str, List[EventHandler]] = {}
        self.projects = ProjectsAPI(self)
        if auto_connect and self._api_key:
            self.connect()

    # ------------------------------------------------------------------ #
    # Connection & auth

    @property
    def connected(self) -> bool:
        return self._transport.connected

    @property
    def username(self) -> Optional[str]:
        return self._credentials.username if self._credentials else None

    def connect(self) -> "TakeoffClient":
        """Exchange the API key for a session token and open the WebSocket."""
        if not self._api_key:
            raise AuthenticationError(
                "No API key found. Pass api_key=, set TAKEOFF_API_KEY, or run "
                "TakeoffClient.setup() once to create and store a key."
            )
        self._credentials = self._auth.exchange_api_key(self._api_key)
        self._transport.connect(self._credentials.access)
        logger.info("Connected to %s as %s", self._transport.url, self.username)
        return self

    def reconnect(self) -> None:
        """Re-open the WebSocket, re-exchanging the API key if the token aged out."""
        self._transport.close()
        if self._credentials is None or self._credentials.expired:
            if not self._api_key:
                raise NotConnectedError("No API key available — construct with api_key=")
            self._credentials = self._auth.exchange_api_key(self._api_key)
        self._transport.connect(self._credentials.access)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "TakeoffClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # One-time interactive setup

    @classmethod
    def setup(cls, base_url: Optional[str] = None, *, save: bool = True) -> str:
        """Interactively create an API key and save it for future scripts.

        Prompts for your username and password ONCE, uses them for a single
        key-creation request, and never stores the password. The new key is
        written to ``~/.takeoff/credentials`` (unless ``save=False``) so later
        ``TakeoffClient()`` calls authenticate with no key in your code.

        Run it from a terminal::

            python -m pytakeoff

        Returns the plaintext key.
        """
        import getpass

        url = (base_url or input(f"Server URL [{_DEFAULT_BASE_URL}]: ").strip()
               or _DEFAULT_BASE_URL)
        url = _normalize_base_url(url)
        username = input("Username: ").strip()
        password = getpass.getpass("Password (used once, never stored): ")
        name = input("Key name [pytakeoff]: ").strip() or "pytakeoff"

        api_key, key_info = AuthSession(url).create_api_key(username, password, name)
        del password

        print(f"\nAPI key '{name}' created (id {key_info.get('key_id', '?')}).")
        if save:
            path = keystore.save(api_key, url)
            print(f"Saved to {path}\n"
                  f"Scripts can now connect with a bare TakeoffClient(). Keep this "
                  f"file private (it holds your key).")
        else:
            print("Shown only once — copy it into your scripts:\n")
            print(f'    API_KEY = "{api_key}"\n')
        print("Manage or revoke your keys anytime in the GUI under Account → API Keys.")
        return api_key

    @classmethod
    def configure(
        cls, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> str:
        """Save an already-created API key to ``~/.takeoff/credentials``.

        Use this when you generated a key in the GUI (Account → API Keys) and
        just want to store it so scripts authenticate with a bare
        ``TakeoffClient()``. No password is involved. Prompts for anything not
        passed::

            python -m pytakeoff configure

        Returns the path to the credentials file.
        """
        if api_key is None:
            api_key = input("Paste your API key (tk_...): ").strip()
        if not (api_key or "").startswith("tk_"):
            raise AuthenticationError(
                "That does not look like an API key; it should start with 'tk_'."
            )
        if base_url is None:
            base_url = (input(f"Server URL [{_DEFAULT_BASE_URL}]: ").strip()
                        or _DEFAULT_BASE_URL)
        url = _normalize_base_url(base_url)
        path = keystore.save(api_key, url)
        print(f"Saved credentials to {path}\n"
              f"Scripts can now connect with a bare TakeoffClient().")
        return str(path)

    # ------------------------------------------------------------------ #
    # Commands

    def call(
        self,
        command: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        on_progress: Optional[ProgressCallback] = None,
        timeout: Any = _UNSET,
        **fields: Any,
    ) -> Any:
        """Send any registered command and return its response payload.

        Payload fields can be passed as a dict, as keyword arguments, or
        both (keyword arguments win)::

            client.call("load_project", name="my_foil")
            client.call("update_entity", {"entity_type": "FoilSection", "data": {...}})

        ``on_progress(percent, message)`` receives progress updates from
        long-running commands (simulations, optimizations, project loads).
        ``timeout`` overrides the client default; pass ``None`` to wait
        forever. Raises :class:`pytakeoff.CommandError` on server-side
        failure — or its subclasses :class:`pytakeoff.RateLimited` (wait
        ``exc.retry_after`` seconds) and :class:`pytakeoff.GuiSessionActive`.

        If the WebSocket died since the last call (server restart, laptop
        sleep, idle timeout — common between notebook cells), the client
        reconnects automatically and retries once, re-exchanging the API
        key if the session token (~1 h) expired. Connections idle past the
        server's ping window (~40 s — an idle synchronous client cannot
        answer pings) are reconnected proactively, before they fail.
        A drop *mid-command* is not retried (the server may have executed
        it) and raises :class:`pytakeoff.ConnectionClosed`.
        """
        merged = dict(payload or {})
        merged.update(fields)
        resolved_timeout = self.timeout if timeout is _UNSET else timeout
        if self._api_key and (
            not self.connected or self._transport.idle_seconds() > _STALE_AFTER
        ):
            self.reconnect()
        try:
            return self._transport.call(
                command, merged, on_progress=on_progress, timeout=resolved_timeout
            )
        except ConnectionClosed as exc:
            # Retry only if the frame never reached the server.
            if getattr(exc, "sent", True) or not self._api_key:
                raise
            self.reconnect()
            return self._transport.call(
                command, merged, on_progress=on_progress, timeout=resolved_timeout
            )

    def commands(self) -> Dict[str, Dict[str, Any]]:
        """List every command the server exposes, with its metadata.

        Fetched live from ``GET /api/permissions/commands/`` — always in
        sync with the running server version.
        """
        response = requests.get(f"{self.base_url}/api/permissions/commands/", timeout=30)
        response.raise_for_status()
        return response.json().get("commands", {})

    # ------------------------------------------------------------------ #
    # Server-initiated events

    def on(self, event: str, handler: EventHandler) -> None:
        """Subscribe to a broadcast event (e.g. ``project_saved``).

        Use ``"*"`` to receive every broadcast. Handlers run inside the
        receive loop of the currently blocking :meth:`call`, so keep them
        fast and never call the client from inside one.
        """
        self._event_handlers.setdefault(event, []).append(handler)

    def _handle_event(self, event: str, message: Dict[str, Any]) -> None:
        for handler in self._event_handlers.get(event, []):
            handler(message)
        for handler in self._event_handlers.get("*", []):
            handler(message)
