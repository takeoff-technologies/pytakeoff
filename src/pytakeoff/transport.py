"""Synchronous WebSocket transport for the Takeoff command protocol.

Wire format, client to server (one JSON text frame per command)::

    {"event": "<command>", "payload": {...}, "message_id": "<hex>"}

Server to client::

    {"event": "<command>_ack", "status": "success|error|partial",
     "payload": {...}, "message_id": "<hex>"}

Rules implemented here:

- Responses are correlated by ``message_id`` + the ``<command>_ack`` event
  name. Frames that do not match the pending call are broadcasts
  (``project_saved``, ``*_properties_updated``, ``job_progress``, ...) and
  are handed to ``on_event``.
- Long-running commands send an immediate acceptance ack
  (``payload.status == "accepted"``), then ``status == "partial"`` progress
  frames, then the final ack — all sharing the original ``message_id``.
- Error text can live in a top-level ``error`` field (MessageBuilder) or in
  ``payload.error`` (consumer-level rejections, which omit ``status``).
- A handful of mesh commands answer with a JSON envelope
  (``payload_type == "flatbuffer"``) followed by one binary frame.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import websocket

from .exceptions import (
    CommandError,
    CommandTimeout,
    ConnectionClosed,
    GuiSessionActive,
    NotConnectedError,
    QueueFull,
    RateLimited,
)

logger = logging.getLogger("pytakeoff")

ProgressCallback = Callable[[Optional[float], Optional[str]], None]
EventCallback = Callable[[str, Dict[str, Any]], None]

# Server error codes that map to dedicated exception types.
_ERROR_CODE_CLASSES = {
    "rate_limited": RateLimited,
    "gui_session_active": GuiSessionActive,
    "queue_full": QueueFull,
}


def _command_error(message: str, command: str, payload: Dict[str, Any]) -> CommandError:
    """Build the most specific CommandError subclass for the server's error code."""
    cls = _ERROR_CODE_CLASSES.get(payload.get("code", ""), CommandError)
    return cls(message, command=command, payload=payload)


@dataclass
class FlatBufferResult:
    """Raw binary answer from a FlatBuffer command (not decoded by pytakeoff)."""

    schema: Optional[str]
    data: bytes
    envelope: Dict[str, Any]


class WebSocketTransport:
    def __init__(self, url: str, *, timeout: float = 120.0) -> None:
        self.url = url
        self.default_timeout = timeout
        self.on_event: Optional[EventCallback] = None
        self._ws: Optional[websocket.WebSocket] = None
        self._last_io = 0.0
        # call() holds this for a whole command round-trip; the keepalive
        # thread only reads the socket when no call is in flight.
        self._io_lock = threading.RLock()
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None

    def idle_seconds(self) -> float:
        """Seconds since the last successful frame in either direction."""
        if self._ws is None:
            return float("inf")
        return time.monotonic() - self._last_io

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.connected

    def connect(self, token: str) -> None:
        separator = "&" if "?" in self.url else "?"
        ws_url = f"{self.url}{separator}token={token}"
        # The server occasionally drops a handshake that lands within
        # milliseconds of a previous disconnect (e.g. scripts run
        # back-to-back), so retry once after a short pause.
        for attempt in (1, 2):
            try:
                self._ws = websocket.create_connection(ws_url, timeout=self.default_timeout)
                self._last_io = time.monotonic()
                self._start_keepalive()
                return
            except Exception as exc:  # handshake refused, DNS, TLS, ...
                if attempt == 2:
                    raise ConnectionClosed(
                        f"Could not open WebSocket to {self.url}: {exc}"
                    ) from exc
                time.sleep(1.0)

    def close(self) -> None:
        self._stop_keepalive()
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    # ------------------------------------------------------------------ #
    # Keepalive: idle WebSockets die quietly — NAT/proxy/port-forward hops
    # (e.g. WSL2's localhost forwarding) drop silent TCP connections, and
    # servers may ping-timeout clients that never read the socket. This
    # daemon thread pings the server when the connection has been quiet and
    # reads the socket while no call() is in flight: pongs prove liveness,
    # incoming pings are answered automatically by the websocket library,
    # and broadcasts received while idle are dispatched to on_event.

    _PING_AFTER = 15.0  # ping when this many seconds pass without traffic

    def _start_keepalive(self) -> None:
        if self._keepalive_thread is not None and self._keepalive_thread.is_alive():
            return
        self._keepalive_stop.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, name="pytakeoff-keepalive", daemon=True
        )
        self._keepalive_thread.start()

    def _stop_keepalive(self) -> None:
        self._keepalive_stop.set()
        thread = self._keepalive_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._keepalive_thread = None

    def _keepalive_loop(self) -> None:
        while not self._keepalive_stop.wait(5.0):
            ws = self._ws
            if ws is None:
                continue
            if not self._io_lock.acquire(blocking=False):
                continue  # a call() is in flight; its recv keeps things alive
            try:
                if self._ws is None:
                    continue
                if time.monotonic() - self._last_io > self._PING_AFTER:
                    self._ws.ping()
                self._ws.settimeout(0.2)
                for _ in range(20):  # drain pongs / pings / broadcasts
                    opcode, frame = self._ws.recv_data(control_frame=True)
                    self._last_io = time.monotonic()
                    if opcode == websocket.ABNF.OPCODE_TEXT:
                        try:
                            message = json.loads(frame)
                        except ValueError:
                            continue
                        self._dispatch(message.get("event", ""), message)
            except websocket.WebSocketTimeoutException:
                pass  # nothing pending — the normal idle case
            except (websocket.WebSocketException, OSError):
                self._ws = None  # dead; the next call() reconnects
            finally:
                self._io_lock.release()

    def call(
        self,
        command: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        on_progress: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send one command and block until its final response.

        Returns the ack payload (a dict for JSON commands, a
        :class:`FlatBufferResult` for binary mesh commands).
        """
        if not self.connected:
            raise NotConnectedError("WebSocket is not connected — call connect() first")
        assert self._ws is not None

        message_id = uuid.uuid4().hex
        ack_event = f"{command}_ack"
        frame = {"event": command, "payload": payload or {}, "message_id": message_id}
        deadline = None if timeout is None else time.monotonic() + timeout

        with self._io_lock:  # keeps the keepalive reader off the socket
            return self._call_locked(
                command, frame, message_id, ack_event, deadline, on_progress
            )

    def _call_locked(
        self,
        command: str,
        frame: Dict[str, Any],
        message_id: str,
        ack_event: str,
        deadline: Optional[float],
        on_progress: Optional[ProgressCallback],
    ) -> Any:
        assert self._ws is not None
        try:
            self._ws.send(json.dumps(frame))
            self._last_io = time.monotonic()
        except (websocket.WebSocketException, OSError) as exc:
            self._ws = None  # dead socket; next call() can reconnect cleanly
            error = ConnectionClosed(f"Send failed: {exc}")
            error.sent = False  # frame never reached the server — safe to retry
            raise error from exc

        while True:
            raw = self._recv(deadline, command)
            if isinstance(raw, bytes):
                # Binary frame we were not waiting for; nothing to do with it.
                logger.debug("Ignoring unexpected binary frame (%d bytes)", len(raw))
                continue

            try:
                message = json.loads(raw)
            except ValueError:
                logger.debug("Ignoring non-JSON frame: %.100s", raw)
                continue

            event = message.get("event", "")
            if event != ack_event or message.get("message_id") != message_id:
                self._dispatch(event, message)
                continue

            # FlatBuffer envelope: the actual payload follows as a binary frame.
            if message.get("payload_type") == "flatbuffer":
                data = self._recv_binary(deadline, command)
                return FlatBufferResult(
                    schema=message.get("schema"), data=data, envelope=message
                )

            status = message.get("status")
            ack_payload = message.get("payload") or {}

            if status == "partial":
                if on_progress:
                    on_progress(ack_payload.get("progress"), ack_payload.get("message"))
                continue

            if (
                status == "success"
                and isinstance(ack_payload, dict)
                and ack_payload.get("status") == "accepted"
            ):
                # Immediate acceptance of an async command; final ack follows.
                if on_progress:
                    on_progress(0.0, ack_payload.get("message") or "accepted")
                continue

            error_text = message.get("error")
            if not error_text and isinstance(ack_payload, dict):
                error_text = ack_payload.get("error")

            if status == "error" or (status is None and error_text):
                raise _command_error(
                    str(error_text or "command failed"),
                    command,
                    ack_payload if isinstance(ack_payload, dict) else {},
                )

            if isinstance(ack_payload, dict) and ack_payload.get("success") is False:
                raise _command_error(
                    str(
                        ack_payload.get("error")
                        or ack_payload.get("message")
                        or "command failed"
                    ),
                    command,
                    ack_payload,
                )

            return ack_payload

    # ------------------------------------------------------------------ #

    def _recv(self, deadline: Optional[float], command: str) -> Any:
        assert self._ws is not None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandTimeout(f"'{command}' did not complete in time")
            self._ws.settimeout(remaining)
        else:
            self._ws.settimeout(None)
        try:
            data = self._ws.recv()
            self._last_io = time.monotonic()
            return data
        except websocket.WebSocketTimeoutException as exc:
            raise CommandTimeout(f"'{command}' did not complete in time") from exc
        except (websocket.WebSocketConnectionClosedException, OSError) as exc:
            # Covers clean closes and OS-level aborts (e.g. WinError 10053
            # after a server restart or laptop sleep).
            self._ws = None
            raise ConnectionClosed(
                "Connection lost (server restarted? machine slept?) — "
                "the next call reconnects automatically"
            ) from exc

    def _recv_binary(self, deadline: Optional[float], command: str) -> bytes:
        """Read frames until the binary FlatBuffer payload arrives."""
        while True:
            raw = self._recv(deadline, command)
            if isinstance(raw, bytes):
                return raw
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            self._dispatch(message.get("event", ""), message)

    def _dispatch(self, event: str, message: Dict[str, Any]) -> None:
        logger.debug("Broadcast received: %s", event)
        if self.on_event is not None:
            try:
                self.on_event(event, message)
            except Exception:  # user handler must not break the recv loop
                logger.exception("Unhandled error in event handler for '%s'", event)
