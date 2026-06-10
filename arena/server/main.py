"""FastAPI application entrypoint.

Intended for local or trusted-network use; do not expose publicly as-is.
Set ARENA_API_TOKEN to require a token on run creation, and leave
ARENA_SERVER_ALLOW_LOCAL_EXECUTION unset so HTTP callers cannot trigger
local command execution.
"""

from fastapi import FastAPI

from arena import __version__
from arena.server.routes import cases, leaderboard, runs

app = FastAPI(title="CodeReview Arena API", version=__version__)
app.include_router(cases.router)
app.include_router(runs.router)
app.include_router(leaderboard.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
