#!/usr/bin/env bash
# AWAGO launcher for macOS / Linux.
# Usage: ./run.sh [--no-browser] [--port 8001] ...
set -euo pipefail
cd "$(dirname "$0")"

# Find a suitable Python (3.10+).
for CANDIDATE in python3 python; do
  if command -v "$CANDIDATE" >/dev/null 2>&1; then
    if "$CANDIDATE" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
      exec "$CANDIDATE" run.py "$@"
    fi
  fi
done

echo "ERROR: Python 3.10+ is required but was not found." >&2
echo "Install it from https://python.org (or your package manager) and re-run ./run.sh" >&2
exit 1
