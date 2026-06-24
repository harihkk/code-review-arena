# RealFix Seed v0 hermetic test image: arena-realfix-seed:0
# Carries no Arena source and no benchmark source. Cases bind-mount their
# materialized tree at /workspace and run with --network none. PYTHONPATH=/workspace/src
# makes src-layout packages (e.g. src/click) importable from the materialized source.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/workspace/src

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /workspace
