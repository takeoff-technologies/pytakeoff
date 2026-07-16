"""API key resolution for :class:`pytakeoff.TakeoffClient`.

Resolution order:

1. ``api_key=`` constructor argument
2. ``TAKEOFF_API_KEY`` environment variable (recommended for CI)
3. A ``~/.takeoff/credentials`` file — JSON
   (``{"api_key": "...", "base_url": "..."}``). Generate it automatically with
   ``python -m pytakeoff`` / :meth:`TakeoffClient.setup` /
   :meth:`TakeoffClient.configure` (all call :func:`save` below), or write it
   by hand.

Never store a key inside a project directory — it would end up committed to
version control. The credentials file lives in your home directory instead.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple

ENV_VAR = "TAKEOFF_API_KEY"
ENV_URL_VAR = "TAKEOFF_URL"

#: The literal placeholder shipped in the examples/README. Leaving it in a
#: script is the same as providing no key: resolution falls through to the
#: env var / credentials file instead of failing with a confusing
#: "Invalid API key" from the server.
PLACEHOLDER_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#: Any all-``x`` variant of the placeholder (real key ids are hex, never all x).
_PLACEHOLDER_RE = re.compile(r"tk_x+_x+", re.IGNORECASE)


def _clean_key(value: Optional[str]) -> Optional[str]:
    """Return a usable key, or ``None`` if empty/whitespace or the placeholder."""
    if not value:
        return None
    stripped = value.strip()
    if not stripped or _PLACEHOLDER_RE.fullmatch(stripped):
        return None
    return stripped


def credentials_path() -> Path:
    return Path.home() / ".takeoff" / "credentials"


def load() -> Tuple[Optional[str], Optional[str]]:
    """Return (api_key, base_url) from the credentials file, or (None, None)."""
    path = credentials_path()
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None, None
    return data.get("api_key"), data.get("base_url")


def save(
    api_key: str, base_url: Optional[str] = None, path: Optional[Path] = None
) -> Path:
    """Write the credentials file so scripts authenticate with no inline key.

    Creates ``~/.takeoff/credentials`` (or ``path``) as JSON
    ``{"api_key": ..., "base_url": ...}``, creating the parent directory if
    needed and restricting the file to the current user (mode ``0600`` where
    the OS supports it). Overwrites any existing file. Returns the path written.
    """
    target = Path(path) if path is not None else credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"api_key": api_key}
    if base_url:
        payload["base_url"] = base_url
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass  # best effort — Windows ACLs differ from POSIX modes
    return target


def resolve_api_key(explicit: Optional[str] = None) -> Optional[str]:
    """Apply the documented resolution order.

    An empty value or the example placeholder key is treated as "not
    provided" — so an unedited example (``api_key="tk_xxxx..."``) falls
    through to ``TAKEOFF_API_KEY`` or the credentials file rather than
    trying, and failing, to authenticate with the placeholder.
    """
    key = _clean_key(explicit)
    if key:
        return key
    key = _clean_key(os.environ.get(ENV_VAR))
    if key:
        return key
    stored, _ = load()
    return _clean_key(stored)


def resolve_base_url(explicit: Optional[str] = None) -> Optional[str]:
    """Base URL from argument, ``TAKEOFF_URL``, or the credentials file."""
    if explicit:
        return explicit
    env = os.environ.get(ENV_URL_VAR)
    if env:
        return env
    _, url = load()
    return url
