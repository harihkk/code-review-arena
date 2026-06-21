"""Pure ASGI middleware enforcing a request-body byte limit before parsing.

Pydantic field limits on the request models run only after Starlette has already
received and buffered the whole body, so they do not bound body memory. This
middleware buffers at most ``max_bytes + 1`` bytes of an incoming body-bearing
request, counting the actual ``http.request`` chunks rather than trusting
``Content-Length`` (which may be absent, understated, or overstated), and returns
a small stable 413 without ever invoking the route when the body is too large.
Within-limit bodies are replayed verbatim, so FastAPI's normal 422 field-location
errors are preserved for malformed-but-small requests.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_TOO_LARGE_BODY = b'{"detail":"Request body exceeds the maximum allowed size"}'


class BodySizeLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only body-bearing HTTP methods are bounded; GET/HEAD/health pass through
        # untouched, as do non-HTTP (lifespan, websocket) scopes.
        if scope["type"] != "http" or scope.get("method", "").upper() not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Client went away mid-body; hand the disconnect to the app and stop.
                await self.app(scope, _replay(bytes(body), disconnected=True), send)
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if chunk:
                # Count actual bytes; never buffer beyond the cap.
                if len(body) + len(chunk) > self.max_bytes:
                    await self._reject(send)
                    return
                body.extend(chunk)
            more_body = message.get("more_body", False)

        await self.app(scope, _replay(bytes(body), disconnected=False), send)

    async def _reject(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_TOO_LARGE_BODY)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _TOO_LARGE_BODY, "more_body": False})


def _replay(body: bytes, *, disconnected: bool) -> Receive:
    """A receive() that yields the buffered body once, then a terminal message."""
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return (
            {"type": "http.disconnect"}
            if disconnected
            else {"type": "http.request", "body": b"", "more_body": False}
        )

    return receive
