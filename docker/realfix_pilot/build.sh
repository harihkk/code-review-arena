#!/usr/bin/env bash
# Build the RealFix Pilot v1 hermetic test image from the pinned lock.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
docker build --tag arena-realfix-pilot:1 "$here"
