#!/usr/bin/env bash
# One command: bring up the stack in containers, run the FULL autotest suite
# (pytest API + Playwright E2E) inside a runner container, write a merged Allure
# report to autotests/allure-report, then tear everything down.
#
# The host needs ONLY Docker — Node, browsers, Python and Allure all live in the
# runner image.
#
#   autotests/scripts/run-containerized.sh [smoke|regression|all]   # default: all
#
# Exit code mirrors the suite result, so it can gate a pre-PR check.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

SUITE="${1:-all}"
export SUITE
COMPOSE=(docker compose -f docker-compose.yaml -f docker-compose.autotests.yml)
PROJECT="jsnotes_autotests"
COMPOSE+=(-p "${PROJECT}")

echo "▶ Preparing env files"
[ -f api/.env ] || cp api/.env.example api/.env
[ -f ui/.env ] || cp ui/.env.example ui/.env

mkdir -p autotests/allure-results autotests/allure-report

cleanup() {
  echo "▶ Tearing down"
  "${COMPOSE[@]}" --profile autotests down -v --remove-orphans
}
trap cleanup EXIT

echo "▶ Building & starting app services (postgres, api, frontend, e2e-proxy)"
"${COMPOSE[@]}" up -d --build postgres api frontend e2e-proxy || exit 1

echo "▶ Running the suite (${SUITE}) in the runner container"
# `run` starts remaining deps (migrations one-off) and blocks until the runner
# exits, propagating its exit code.
"${COMPOSE[@]}" run --rm --build autotests
status=$?

echo "▶ Suite finished with exit ${status}"
echo "  Allure results: autotests/allure-results"
echo "  Allure report:  autotests/allure-report/index.html"
exit ${status}
