"""Exception hierarchy for pytakeoff."""

from __future__ import annotations

from typing import Any, Dict, Optional


class TakeoffError(Exception):
    """Base class for all pytakeoff errors."""


class AuthenticationError(TakeoffError):
    """Login, token refresh, or WebSocket authentication failed."""


class NotConnectedError(TakeoffError):
    """A command was issued while the WebSocket is not connected."""


class ConnectionClosed(TakeoffError):
    """The server closed the WebSocket connection."""


class CommandTimeout(TakeoffError):
    """No final response arrived within the allotted time."""


class CommandError(TakeoffError):
    """The server answered a command with an error.

    Attributes:
        command: the command name that failed.
        payload: the full ack payload, which may carry structured details
            such as ``error_code`` or ``missing_sections``.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.payload = payload or {}


class RateLimited(CommandError):
    """The server throttled this command (API connections are rate limited).

    Attributes:
        retry_after: seconds to wait before retrying (from the server).
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after: float = float(self.payload.get("retry_after", 1))


class QueueFull(CommandError):
    """Too many heavy commands outstanding for your account.

    The server runs one heavy command per account at a time and queues a few
    more (``max_queued`` in the payload); beyond that, new heavy commands are
    rejected. Wait for a queued command to finish before sending the next one.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.max_queued: int = int(self.payload.get("max_queued", 0))


class GuiSessionActive(CommandError):
    """The command is blocked because your GUI (browser) session is connected.

    Project switching/closing commands are rejected while the same account has
    a live browser session, because the script and the GUI share one
    server-side project. Close the browser tab or run the script without the
    GUI open.
    """
