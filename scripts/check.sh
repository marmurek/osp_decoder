#!/bin/sh
# Runs formatting, type, lint and test checks inside the dev image.
set -eu
cd "$(dirname "$0")/.."
docker build --quiet --target dev --tag osp-decoder:dev . >/dev/null
exec docker run --rm --user "$(id -u):$(id -g)" --volume "$PWD:/work" osp-decoder:dev sh -c '
    uv sync --quiet &&
    uv run black --check osp_decoder tests &&
    uv run mypy osp_decoder tests &&
    uv run pylint --fail-under=10.0 osp_decoder tests &&
    uv run pytest --cov=osp_decoder --cov-report=term-missing "$@"
' sh "$@"
