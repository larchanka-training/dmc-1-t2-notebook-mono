#!/usr/bin/env bash
# Wait until the local API is healthy before running tests.
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
TIMEOUT="${TIMEOUT:-120}"

echo "Waiting for API at ${API_BASE_URL}/health (timeout ${TIMEOUT}s)…"
deadline=$(( SECONDS + TIMEOUT ))
until curl -fsS "${API_BASE_URL}/health" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "ERROR: API did not become healthy within ${TIMEOUT}s." >&2
    exit 1
  fi
  sleep 2
done
echo "API is up."
