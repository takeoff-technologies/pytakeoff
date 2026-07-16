"""REST authentication against the Takeoff backend — API keys only.

pytakeoff never holds account passwords. Scripts authenticate with an API key
(``tk_...``), which is exchanged for a short-lived session token:

    POST /api/auth/api-token/   {"api_key": "tk_..."}
                                -> {"access", "expires_in", "username"}

The one exception is the interactive, one-time :func:`create_api_key`
bootstrap used by ``TakeoffClient.setup()``: it uses the password for a single
login + key-creation round trip and never stores it.

    POST /api/auth/login/       {"username", "password"} -> {"access", ...}
    POST /api/auth/keys/        {"name", "expires_in_days"?}
                                -> {"api_key": "tk_...", "key": {...}}

Rate limits, credits, and permissions are enforced server-side; connections
authenticated with an API key are throttled by the server (see
:class:`pytakeoff.RateLimited`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import requests

from .exceptions import AuthenticationError

# Re-exchange the API key this many seconds before the session token expires.
_EXPIRY_MARGIN = 30.0


@dataclass
class Credentials:
    """A short-lived API session token obtained from an API key."""

    access: str
    expires_at: float = 0.0
    username: Optional[str] = None

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - _EXPIRY_MARGIN


def _error_detail(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    if isinstance(data, dict):
        for key in ("detail", "error", "message"):
            if data.get(key):
                return str(data[key])
        # DRF field errors: {"non_field_errors": ["..."], "password": ["..."]}
        parts = [
            f"{field}: {'; '.join(map(str, msgs)) if isinstance(msgs, list) else msgs}"
            for field, msgs in data.items()
        ]
        if parts:
            return " | ".join(parts)
    return f"HTTP {response.status_code}"


class AuthSession:
    """Exchanges API keys for session tokens over REST."""

    def __init__(self, base_url: str, session: Optional[requests.Session] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = session or requests.Session()

    def _post(self, path: str, json: Optional[dict] = None, token: Optional[str] = None) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        response = self._http.post(
            f"{self.base_url}{path}", json=json or {}, headers=headers, timeout=30
        )
        if response.status_code >= 400:
            raise AuthenticationError(_error_detail(response))
        return response.json()

    def exchange_api_key(self, api_key: str) -> Credentials:
        """Turn an API key into a short-lived session token."""
        data = self._post("/api/auth/api-token/", {"api_key": api_key})
        return Credentials(
            access=data["access"],
            expires_at=time.time() + float(data.get("expires_in", 3600)),
            username=data.get("username"),
        )

    def create_api_key(
        self,
        username: str,
        password: str,
        name: str,
        expires_in_days: Optional[int] = None,
    ) -> Tuple[str, dict]:
        """One-time interactive bootstrap: login, mint a key, forget the password.

        Returns ``(plaintext_key, key_info)``. The plaintext key is shown only
        once by the server — store it (``TakeoffClient.setup()`` does this for
        you via :mod:`pytakeoff.keystore`).
        """
        login = self._post("/api/auth/login/", {"username": username, "password": password})
        body: dict = {"name": name}
        if expires_in_days:
            body["expires_in_days"] = int(expires_in_days)
        data = self._post("/api/auth/keys/", body, token=login["access"])
        return data["api_key"], data.get("key", {})
