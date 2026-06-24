#!/usr/bin/env bash
# Build the RealFix Seed v0 hermetic test image from the pinned lock.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
docker build --tag arena-realfix-seed:0 "$here"
