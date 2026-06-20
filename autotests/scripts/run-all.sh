#!/usr/bin/env bash
# Run both suites (pytest API + Playwright E2E) against an ALREADY-RUNNING stack
# and produce a single merged Allure report.
#
# This is the inner runner — it assumes the API and UI are reachable (it waits
# for them). To bring the stack up/down around it, use run-containerized.sh.
#
# Env:
#   API_BASE_URL        backend base for pytest + E2E node-side helpers
#   BASE_URL            UI origin the browser visits
#   PYTHON              python interpreter (default: python)
#   PLAYWRIGHT_PROJECT  restrict E2E to one project (e.g. chromium); empty = all
#
# Usage: run-all.sh [smoke|regression|all]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUITE="${1:-all}"
RESULTS="${HERE}/allure-results"
REPORT="${HERE}/allure-report"
PYTHON="${PYTHON:-python}"

export API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
export BASE_URL="${BASE_URL:-http://notebook.com}"

# Clear prior results/report CONTENTS (the dirs may be bind-mounts → don't rm them).
mkdir -p "${RESULTS}/api" "${RESULTS}/e2e" "${REPORT}"
rm -rf "${RESULTS:?}/api/"* "${RESULTS:?}/e2e/"* "${REPORT:?}/"* 2>/dev/null || true

# Wait for API, then for the UI to actually serve the app shell. The Vite dev
# server cold-starts slowly (deps populate into a fresh volume), so allow ~5 min.
"${HERE}/scripts/wait-for-stack.sh" || exit 1
echo "Waiting for UI at ${BASE_URL} …"
for i in $(seq 1 150); do
  if curl -fsS "${BASE_URL}" 2>/dev/null | grep -q '<div id="root">'; then echo "UI is up."; break; fi
  [ "$i" = "150" ] && { echo "ERROR: UI not ready at ${BASE_URL}" >&2; exit 1; }
  sleep 2
done

api_status=0
e2e_status=0

# ---- API suite (pytest + allure-pytest) ----
echo "=== API suite (pytest) ==="
PYTEST_ARGS=()
case "${SUITE}" in
  smoke) PYTEST_ARGS=(-m smoke) ;;
  regression) PYTEST_ARGS=(-m "smoke or regression") ;;
esac
( cd "${HERE}/api" && "${PYTHON}" -m pytest "${PYTEST_ARGS[@]}" --alluredir "${RESULTS}/api" ) || api_status=$?

# ---- E2E suite (Playwright + allure-playwright) ----
echo "=== E2E suite (Playwright) ==="
PW_ARGS=()
case "${SUITE}" in
  smoke) PW_ARGS+=(--grep @smoke) ;;
  regression) PW_ARGS+=(--grep "@smoke|@regression") ;;
esac
[ -n "${PLAYWRIGHT_PROJECT:-}" ] && PW_ARGS+=(--project "${PLAYWRIGHT_PROJECT}")
( cd "${HERE}/e2e" && npx playwright test "${PW_ARGS[@]}" ) || e2e_status=$?

# ---- Merge + generate Allure report ----
echo "=== Generating Allure report ==="
if command -v allure >/dev/null 2>&1; then
  allure generate "${RESULTS}/api" "${RESULTS}/e2e" --clean -o "${REPORT}"
  echo "Allure report: ${REPORT}/index.html  (open with: allure open '${REPORT}')"
else
  echo "WARNING: 'allure' CLI not found — results are in ${RESULTS}/{api,e2e}." >&2
  echo "Install: https://allurereport.org/docs/install/  (needs Java)." >&2
fi

echo "API exit=${api_status}  E2E exit=${e2e_status}"
[[ ${api_status} -eq 0 && ${e2e_status} -eq 0 ]]
