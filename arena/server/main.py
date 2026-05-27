"""FastAPI application entrypoint."""

from fastapi import FastAPI

from arena import __version__
from arena.server.routes import cases, leaderboard, runs

app = FastAPI(title="Code Review Arena API", version=__version__)
app.include_router(cases.router)
app.include_router(runs.router)
app.include_router(leaderboard.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
