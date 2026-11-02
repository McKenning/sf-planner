#!/bin/sh
# Run pytest inside the python:3.12 image (the runtime version) before each deploy.
# Repo is mounted read-only; ~/sf-inputs is mounted so Docs/1.x-snapshot tests run, not skip.
set -e
cd "$(dirname "$0")/.."
exec docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD":/src:ro -v "$HOME/sf-inputs":/root/sf-inputs:ro python:3.12-slim \
  sh -c 'cp -r /src /app && cd /app && pip install -q --root-user-action=ignore -r requirements-dev.txt 2>&1 | tail -1; python -V && python -m pytest -q'
