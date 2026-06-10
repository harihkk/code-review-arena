"""Optional token authentication and execution opt-ins for the API server.

The server is meant for local and trusted-network use. It is not safe to
expose publicly: set ARENA_API_TOKEN to require a token on run creation, and
leave ARENA_SERVER_ALLOW_LOCAL_EXECUTION unset so HTTP callers cannot trigger
local command execution at all.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def server_local_execution_enabled() -> bool:
    return os.getenv("ARENA_SERVER_ALLOW_LOCAL_EXECUTION", "").lower() in {"1", "true", "yes"}


def require_api_token(
    x_arena_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Reject the request when ARENA_API_TOKEN is set and not presented."""
    expected = os.getenv("ARENA_API_TOKEN")
    if not expected:
        return
    provided = x_arena_token
    if provided is None and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[len("bearer ") :]
    if provided is None or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")
