#!/bin/sh
# Run pytest inside the python:3.12 image (the runtime version) before each deploy.
# Repo is mounted read-only; ~/sf-inputs is mounted so Docs/1.x-snapshot tests run, not skip.
# 1.x's backend/ is copied next to the app so the parity test can import 1.x's solver (read-only use).
set -e
cd "$(dirname "$0")/../.."
exec docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD":/repo:ro -v "$HOME/sf-inputs":/root/sf-inputs:ro python:3.12-slim \
  sh -c 'cp -r /repo/v2 /app && cp -r /repo/backend /backend && rm -rf /app/.venv && cd /app && pip install -q --root-user-action=ignore -r requirements-dev.txt 2>&1 | tail -1; python -V && python -m pytest -q'
