#!/usr/bin/env bash
# Build the benchmark sandbox image the shipped packs run their tests in.
#
# The tag here MUST match default_docker_image in benchmark_sets/*/manifest.yaml.
# The executor never pulls a missing image (it would run unvetted code from the
# network), so this image has to be built locally before a Docker-backed run or
# certify-pack can execute. Without it, runs cleanly skip and report invalid.
set -euo pipefail

IMAGE_TAG="${ARENA_BENCH_IMAGE:-arena-bench:1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Building ${IMAGE_TAG} from Dockerfile.bench ..."
docker build -f "${ROOT}/Dockerfile.bench" -t "${IMAGE_TAG}" "${ROOT}"
echo "Built ${IMAGE_TAG}."
