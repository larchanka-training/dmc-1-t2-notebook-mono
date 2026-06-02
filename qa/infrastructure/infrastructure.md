# Infrastructure Test Cases

**Feature:** Docker, CI/CD pipeline, deployment  
**Tools:** Docker CLI, GitHub Actions, curl  
**Priority scope:** Smoke, Regression

---

## TC-INFRA-01 — All Docker containers start successfully

**Priority:** Smoke

| Step | Action | Expected Result |
|---|---|---|
| 1 | Run `docker compose up --build -d` | Build completes without errors |
| 2 | Run `docker ps` | 5 containers running: frontend, api, postgres, pgadmin, proxy |
| 3 | Check postgres health | Status: `healthy` |
| 4 | Wait 30 seconds | All containers still running (no restarts) |

**Pass criteria:** All 5 containers running and stable  
**Fail criteria:** Any container exits, build fails, postgres unhealthy

---

## TC-INFRA-02 — API health check endpoint

**Priority:** Smoke  
**Endpoint:** `GET https://api.notebook.com/health`

| Field | Value |
|---|---|
| Expected status | `200` |
| Expected body | `{ "status": "ok" }` or equivalent |
| Expected response time | < 1 second |

**Pass criteria:** 200 within 1 second  
**Fail criteria:** Timeout, 500, non-200 status

---

## TC-INFRA-03 — Frontend loads within performance budget

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open `https://notebook.com` | — |
| 2 | Measure total page load time | < 2.5 seconds |
| 3 | Check JS bundle size in Network tab | < 7 MB |
| 4 | Check for console errors | None |

**Pass criteria:** Load < 2.5s, bundle < 7 MB, no errors  
**Fail criteria:** Slow load, oversized bundle, console errors on initial render

---

## TC-INFRA-04 — Database migrations run successfully

**Priority:** Smoke

| Step | Action | Expected Result |
|---|---|---|
| 1 | Start containers fresh (no existing DB volume) | — |
| 2 | Check API container logs | Migrations applied without errors |
| 3 | Connect to postgres via pgAdmin | Tables: `users`, `sessions`, `notebooks`, `notebook_cells` exist |

**Pass criteria:** All expected tables created  
**Fail criteria:** Migration errors, tables missing, API crashes on start

---

## TC-INFRA-05 — Proxy routes traffic correctly

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | `curl -sk https://notebook.com/` | HTTP 200 |
| 2 | `curl -sk https://api.notebook.com/health` | HTTP 200 |
| 3 | `curl -sk https://pgadmin.notebook.com/` | HTTP 200 or 302 |
| 4 | `curl -sk http://notebook.com/` | HTTP 301 redirect to HTTPS |

**Pass criteria:** All routes correctly forwarded  
**Fail criteria:** Wrong routing, 502 bad gateway, direct port access bypasses proxy

---

## TC-INFRA-06 — CI pipeline runs on pull request

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Open a PR against `main` | — |
| 2 | Check GitHub Actions | Workflow triggered |
| 3 | Verify steps run | Lint → Unit tests → API tests → Docker build |
| 4 | All checks pass | PR shows green checks |

**Pass criteria:** All CI checks pass, merge not blocked  
**Fail criteria:** CI not triggered, steps skipped, false pass on failing tests

---

## TC-INFRA-07 — Container restart recovery

**Priority:** Edge

| Step | Action | Expected Result |
|---|---|---|
| 1 | All containers running | — |
| 2 | `docker restart t2-mono-api-1` | Container restarts |
| 3 | Wait 10 seconds | API container running again |
| 4 | Call `GET /health` | 200 returned |
| 5 | Verify DB connection re-established | API serves authenticated requests |

**Pass criteria:** API recovers automatically after restart  
**Fail criteria:** API stuck in crash loop, DB connection not restored

---

## TC-INFRA-08 — Docker Compose prod config validates

**Priority:** Regression

| Step | Action | Expected Result |
|---|---|---|
| 1 | Run `docker compose -f docker-compose.prod.yaml config` | No errors output |
| 2 | Check all required env vars documented | `.env.prod.example` covers all vars |
| 3 | Verify no dev-only settings in prod config | No `--reload`, no volume mounts of source |

**Pass criteria:** Prod config valid, no dev settings leaked  
**Fail criteria:** Config errors, missing env vars, dev flags in prod
