# Performance Report — Sprint 3

**Issue:** `larchanka-training/js-notebook#154`
**Date:** 2026-06-19
**Scope:** JS Notebook production/performance baseline for the release show

## 1. Executive Summary

The Sprint 3 performance baseline covers the four measurements requested in
`larchanka-training/js-notebook#154`: notebook/page open time, cell execution
time, frontend bundle size, and API latency.

Overall result:

- The public API health path is stable in this low-volume probe: production
  p95 is `197.67 ms` with `50/50` successful responses.
- The execution runtime is fast for small synthetic cells: warm QuickJS/Web
  Worker runs are sub-millisecond to about `1.56 ms` p95, and the timeout path
  stops an infinite loop at about the configured `200 ms` deadline.
- Authenticated notebook API latency is stable in this smoke pass:
  authenticated list/get p95 is about `193 ms` / `191 ms`; a 10-sample patch
  run had one slower tail sample and p95 `786.81 ms`.
- Cloud LLM smoke succeeded with `3/3` Bedrock-backed requests. The small prompt
  p50 was `1.56 s`, p95/max `1.58 s`, using
  `eu.amazon.nova-lite-v1:0`.
- Warm app-shell load is fast (`124 ms` LCP) once assets are cached.
- Cold first-load performance is the release risk: production login/app-shell
  LCP is `4.44 s`, mostly because the main JavaScript asset is served through
  CloudFront without gzip/brotli compression and transfers about `7.93 MB`.
- The authenticated cold app-shell path confirms the same bottleneck: FCP
  `4.86 s`, DOMContentLoaded `4.81 s`, and about `8.13 MiB` transferred.
- The local production build also shows a bundle-size risk: total production
  assets are `9.90 MiB` raw / `4.19 MiB` gzip, and the main JS chunk alone is
  `7.56 MiB` raw.

Primary recommendation before or immediately after release: enable compression
for CloudFront/S3 static JS/CSS assets and then split the main bundle so browser
LLM/editor/runtime code is not all on the first app-shell path.

## 2. Environment

### Repository Baseline

| Area | Branch | Commit SHA |
|---|---|---|
| Monorepo | `feature/api56-result-kind-text` | `0e12ba43c952011c84302ba49d976fd0d7b45337` |
| `ui/` submodule | `feature/api56-result-kind-text` | `03b4fcf73465e83a416f5ee7be807674c70d21af` |
| `api/` submodule | `feature/api56-result-kind-text` | `5aa421d6c4d7bd00a77721fef5e0644f4eefcff8` |

### Targets and Tools

| Item | Value |
|---|---|
| Production URL | `https://jsnb.org` |
| Preview URL | `https://d2e2ymc27fdfn5.cloudfront.net` |
| UI package manager | `pnpm@9.15.9` |
| UI build command | `cd ui && pnpm build` |
| Vite version observed during build | `8.0.16` |
| Browser used for page-load fallback | `Chrome/149.0.7827.115`, headless |
| Page-load viewport | `1440x900` |

`docs/qa-plan.md` lists two relevant targets:

- average page load time: `< 2.5 sec`;
- frontend bundle size: `< 7 MB`.

## 3. Methodology

This was a release baseline, not a stress test.

- Bundle size was measured from a local production Vite build.
- API latency was measured with 50 sequential requests per health endpoint,
  no concurrency and no write operations.
- Browser page load was measured against production using headless Chrome and
  Chrome DevTools Protocol because the in-app Browser plugin was unavailable and
  Playwright/Lighthouse were not installed.
- Cell execution was measured at the runtime/model layer using the same public
  APIs covered by UI acceptance tests: `runInWorker` and `runCell`.
- Authenticated notebook API and Cloud LLM smoke measurements were added after a
  test email/OTP was provided. The user approved up to 5 production Bedrock
  requests; this run used 3.
- The LLM smoke stored only metadata: status, latency, model, tier, token
  counts, prompt byte size, and generated-content byte size. It did not store
  OTP, JWT/refresh tokens, raw prompt, or raw generated content.

Raw working data was collected locally under
`_private/notes/sprint3/performance/`. That directory is intentionally not part
of the public repository; the report keeps the reproducible commands,
methodology, and summarized measurements.

## 4. Notebook/Page Open Results

Measured production anonymous app-shell/login path:

```text
https://jsnb.org/ → https://jsnb.org/login?from=%2F
```

The first table is anonymous app-shell/login performance, not a full
authenticated notebook-open measurement.

| Scenario | FCP | LCP | DOMContentLoaded | Transfer | Notes |
|---|---:|---:|---:|---:|---|
| Cold app-shell | `4,444 ms` | `4,444 ms` | `4,429.70 ms` | `7.96 MiB` | cache cleared/disabled |
| Warm app-shell | `124 ms` | `124 ms` | `102.90 ms` | `379 B` | browser cache enabled |

Cold-load largest resources:

| Resource | Type | Duration | Transfer |
|---|---|---:|---:|
| `/assets/index-Cpd3W_8V.js` | script | `3,832.3 ms` | `7,930,914 B` |
| `/favicon.png` | image | `214.9 ms` | `229,851 B` |
| `/assets/index-6uUYcbzk.css` | CSS | `146.2 ms` | `119,361 B` |
| `/api/v1/notebooks?limit=200` | fetch | `220.0 ms` | `379 B` |

Static asset headers confirmed the main issue:

| Asset | `content-encoding` | `content-length` | `x-cache` |
|---|---|---:|---|
| `/assets/index-Cpd3W_8V.js` | `null` | `7,930,614` | `Hit from cloudfront` |
| `/assets/index-6uUYcbzk.css` | `null` | `119,061` | `Hit from cloudfront` |

Interpretation: first-time users download raw JS/CSS from CloudFront. The cold
app-shell LCP is above the `< 2.5 sec` target, and the largest measured cause is
the uncompressed main JavaScript transfer.

Authenticated app-shell timing was measured in a second run by seeding the
validated session into `localStorage` before application startup. This exercises
the authenticated shell and `/api/v1/auth/me` boot request, but still does not
script user interaction inside a specific notebook. Chrome did not expose LCP in
this CDP run, so FCP and DOMContentLoaded are reported.

| Scenario | FCP | DOMContentLoaded | Wall duration | Transfer | Notes |
|---|---:|---:|---:|---:|---|
| Authenticated cold app-shell | `4,856 ms` | `4,807.30 ms` | `7,811.38 ms` | `8.13 MiB` | cache disabled |
| Authenticated warm app-shell | `184 ms` | `154.40 ms` | `3,158.58 ms` | `1,006 B` | cache enabled |

Authenticated cold-load largest resources:

| Resource | Type | Duration | Transfer |
|---|---|---:|---:|
| `/assets/index-Cpd3W_8V.js` | script | `4,236.8 ms` | `7,930,914 B` |
| `/favicon.png` | image | `799.6 ms` | `229,851 B` |
| `/assets/worker-DOb6psGk.js` | worker | `66.1 ms` | `178,104 B` |
| `/assets/index-6uUYcbzk.css` | CSS | `141.0 ms` | `119,361 B` |
| `/api/v1/auth/me` | fetch | `209.8 ms` | `406 B` |

Interpretation: authentication itself is not the dominant browser-load cost.
The authenticated cold path is again dominated by the raw main JavaScript
transfer.

## 5. Cell Execution Results

Cell execution was measured with synthetic snippets at the runtime/model layer.
This validates the QuickJS/Web Worker path used by the UI but does not include
browser click handling, CodeMirror editing, React paint, or authenticated
notebook opening.

Payloads:

```js
console.log("hello")
```

```js
Array.from({ length: 10000 }, (_, i) => i).reduce((a, b) => a + b, 0)
```

```js
throw new Error("test")
```

Timeout payload:

```js
while (true) {}
```

### `runInWorker`

| Scenario | Samples | Status | Mean | p50 | p95 |
|---|---:|---|---:|---:|---:|
| `hello-first` | 1 | `done` | `36.22 ms` | `36.22 ms` | `36.22 ms` |
| `reduce-first` | 1 | `done` | `4.77 ms` | `4.77 ms` | `4.77 ms` |
| `error-first` | 1 | `error` | `1.26 ms` | `1.26 ms` | `1.26 ms` |
| `timeout-first` | 1 | `timeout` | `200.97 ms` | `200.97 ms` | `200.97 ms` |
| `hello-warm` | 10 | `done` | `0.18 ms` | `0.13 ms` | `0.49 ms` |
| `reduce-warm` | 10 | `done` | `1.29 ms` | `1.26 ms` | `1.56 ms` |
| `error-warm` | 10 | `error` | `0.16 ms` | `0.13 ms` | `0.29 ms` |

### `runCell`

| Scenario | Samples | Status | Duration |
|---|---:|---|---:|
| `hello` | 1 | `done` | `6.45 ms` |
| `reduce` | 1 | `done` | `1.35 ms` |
| `error` | 1 | `error` | `0.31 ms` |

Interpretation: for small synthetic cells, the execution runtime is not the
current bottleneck. The cold app-shell/static asset path is much more expensive
than measured QuickJS execution.

## 6. Bundle Size Results

Command:

```bash
cd ui
pnpm build
```

The build succeeded and Vite emitted this warning:

```text
Some chunks are larger than 500 kB after minification.
Consider using dynamic import() to code-split the application.
```

Production asset totals, excluding local `.DS_Store`:

| Metric | Value |
|---|---:|
| Asset count | `77` |
| Total raw size | `10,382,451 B` / `9.90 MiB` |
| Total gzip size | `4,394,915 B` / `4.19 MiB` |
| Total JS raw | `8,106,719 B` / `7.73 MiB` |
| Total JS gzip | `2,785,499 B` / `2.66 MiB` |
| Total CSS raw | `148,950 B` / `0.14 MiB` |
| Total CSS gzip | `29,825 B` / `0.03 MiB` |
| QuickJS/WASM raw | `503,134 B` / `0.48 MiB` |
| QuickJS/WASM gzip | `234,043 B` / `0.22 MiB` |

Largest local production assets:

| Asset | Raw | Gzip |
|---|---:|---:|
| `assets/index-ftg5C7wP.js` | `7.56 MiB` | `2.61 MiB` |
| `assets/emscripten-module-uFzwHH0Y.wasm` | `0.48 MiB` | `0.22 MiB` |
| `favicon.png` | `0.22 MiB` | `0.22 MiB` |
| `assets/worker-Cr3Qlr2f.js` | `0.17 MiB` | `0.05 MiB` |
| `assets/index-DK9yL0sb.css` | `0.11 MiB` | `0.02 MiB` |

Against the `< 7 MB` target:

- raw total assets exceed the target;
- raw JS exceeds the target;
- the main raw JS chunk exceeds the target by itself;
- gzip totals are below the target, but production currently serves JS/CSS
  uncompressed, so users pay the raw transfer cost on cold load.

Without a bundle analyzer, exact module attribution is not proven. A string scan
of the largest JS chunk found markers for `webllm`, `QuickJS`, `CodeMirror`,
`remark`, `rehype`, `katex`, and `lucide`, suggesting that browser AI, notebook
runtime/editor, markdown/math rendering, and UI icon code are all in the main
chunk.

## 7. API Latency Results

Low-volume sequential health checks:

- 50 samples per endpoint;
- about 200 ms between samples;
- no concurrency;
- no write operations.

| Endpoint | Success | p50 | p95 | p99/max |
|---|---:|---:|---:|---:|
| Production `https://jsnb.org/api/v1/health` | `50/50` | `180.44 ms` | `197.67 ms` | `451.60 ms` |
| Preview `https://d2e2ymc27fdfn5.cloudfront.net/api/v1/health` | `50/50` | `175.28 ms` | `198.51 ms` | `420.87 ms` |

Authenticated production notebook API smoke was measured with a temporary
notebook. The script created one notebook, measured list/get/patch operations,
then soft-deleted it. Cleanup succeeded with `204` in `142.70 ms`.

| Endpoint group | Samples | Success | p50 | p95 | p99/max |
|---|---:|---:|---:|---:|---:|
| `GET /api/v1/notebooks` | `20` | `20/20` | `188.35 ms` | `193.40 ms` | `435.25 ms` |
| `POST /api/v1/notebooks` | `1` | `1/1` | `151.17 ms` | `151.17 ms` | `151.17 ms` |
| `GET /api/v1/notebooks/{id}` | `20` | `20/20` | `183.70 ms` | `191.04 ms` | `411.20 ms` |
| `PATCH /api/v1/notebooks/{id}` | `10` | `10/10` | `188.66 ms` | `786.81 ms` | `786.81 ms` |

Interpretation: the public API health path and authenticated notebook list/get
paths are responsive in low-volume probes. The patch run had one slower tail
sample; this should be rechecked with a larger sample before setting an SLA.

## 8. LLM Latency

Cloud LLM latency was measured with an authenticated production smoke test. The
prompt was intentionally small and non-private. Raw prompt and raw generated
content were not persisted.

Contract evidence from `api/docs/openapi.json`:

| Field | Value |
|---|---|
| Endpoint | `/api/v1/llm/generate` |
| Security | `HTTPBearer` |
| `401` | missing or invalid access token |
| `429` | per-user LLM rate limit exceeded |
| `502` | Bedrock provider failed |
| `504` | generation pipeline exceeded deadline |

Smoke result:

| Metric | Value |
|---|---:|
| Approved max production Bedrock requests | `5` |
| Actual requests | `3` |
| Success | `3/3` |
| Model | `eu.amazon.nova-lite-v1:0` |
| Tier | `backend` |
| Prompt size | `64 B` |
| Tokens per request | `75 prompt / 20 completion` |
| min | `831.12 ms` |
| p50 | `1,563.06 ms` |
| p95/max | `1,579.72 ms` |

Interpretation: the small-prompt cloud path is comfortably below the documented
30-second pipeline deadline in this smoke test. This is not a load test and does
not cover large context windows, guard rejection, repair retries, throttling, or
provider failures.

## 9. Bottlenecks

1. **Uncompressed production static assets.** The main production JS file is
   served with `content-encoding: null`, so cold users download about `7.93 MB`
   of JS for the app shell.
2. **Single large main JS chunk.** The local production build emits a main JS
   chunk of `7.56 MiB` raw / `2.61 MiB` gzip and Vite warns about chunk size.
3. **Cold app-shell load exceeds the page-load target.** Measured LCP/FCP is
   `4.44 s`, above the `< 2.5 sec` target in `docs/qa-plan.md`.
4. **Patch latency has an outlier in a small sample.** Authenticated patch p95
   was `786.81 ms` across only 10 samples. This is not a release blocker from
   the current data, but it needs more samples before setting a sync SLA.
5. **No full scripted notebook interaction metric yet.** The authenticated
   browser run exercises the app shell and boot auth request, but not clicking a
   specific notebook, editing a cell, rendering output, or syncing from the UI.
6. **No real-user cell duration telemetry.** Synthetic runtime results are fast,
   but production user devices, output rendering, large notebooks, and real code
   are not represented.
7. **Large notebooks can still overload the browser.** The backend and remote
   sync contract cap a notebook at 500 cells, but the current editor renders the
   cell list directly from the in-memory model. A local-first user can create a
   large notebook before any backend request happens, so UI rendering cost can
   grow independently from API, database, or Bedrock latency.

## 10. Recommended Improvements

Priority 1:

- Enable gzip/brotli compression for CloudFront/S3 JS and CSS assets.
- Confirm immutable caching headers for hashed assets. The observed `HEAD`
  response for JS/CSS had no `cache-control` header.

Priority 2:

- Code-split the main bundle. Start with lazy-loading WebLLM/browser AI code and
  other heavy notebook/editor modules that are not required for the first app
  shell.
- Add an approved bundle analyzer in a follow-up to replace string-scan
  inference with exact module attribution.

Priority 3:

- Reduce `favicon.png` size. It transferred about `230 KB` on cold load.
- Add metadata-only analytics for real `cell.executed` durations, including
  status, tier, duration, and code size, without logging source code.
- Add a Playwright or Chrome-CDP scripted authenticated notebook scenario:
  login/session seed, open a specific notebook, edit/run one cell, and record
  Web Vitals plus API timings.
- Repeat authenticated patch/sync latency with at least 50 samples before
  treating p95 as a release metric.

Large-notebook optimization path:

- Keep the existing backend/sync hard cap of 500 cells as a release safety
  guard, and mirror it in local UI creation so users do not build an unsyncable
  notebook in the browser.
- Add a softer UX warning around 150-200 cells until large-notebook rendering is
  measured on lower-memory devices.
- Treat JupyterLab-style notebook windowing as the target architecture for
  larger notebooks: keep every cell in the notebook model/state, but mount only
  the visible cells plus a small overscan window in the DOM.
- Preserve `Run all` semantics by executing over the model/state, not over the
  rendered DOM. Hidden or unmounted cells can still run because their source,
  status, and output live in state; when the user scrolls to them, the UI reads
  the already updated state.
- Separately cap or collapse very large outputs. One large output can be more
  expensive than many small cells, so output trimming is a separate performance
  control from the cell-count cap.

## 11. Risks and Untested Areas

- Full authenticated notebook interaction path is only partially tested: the
  authenticated browser app shell and `/auth/me` boot request were measured, but
  a scripted open/edit/run/sync flow was not.
- Authenticated notebook CRUD latency was measured as API smoke, not as a UI
  workflow.
- Cloud LLM generation latency was measured with 3 small-prompt requests only;
  large contexts, guard rejection, repair retries, throttling, provider errors,
  and concurrency were not tested.
- INP: not measured because the browser run did not include real user
  interaction.
- Browser page-load data is one reliable cold sample and one reliable warm
  sample, not a statistical distribution.
- Cell execution was measured in Vitest/jsdom with `@vitest/web-worker`, not as
  a full production browser click-through.
- Large-notebook browser behavior was not measured with 500+ cells. Current
  evidence supports adding a local guard and planning JupyterLab-style windowing,
  but it does not yet quantify the exact freeze threshold on 8 GB / 16 GB
  machines.
- High-concurrency load testing was intentionally out of scope.
- No new dependencies were installed, so no Lighthouse or bundle visualizer
  report is included.

## 12. Appendix: Local Evidence and Commands

Local-only raw evidence, intentionally not committed:

```text
_private/notes/sprint3/performance/baseline.md
_private/notes/sprint3/performance/bundle-size.md
_private/notes/sprint3/performance/api-latency.md
_private/notes/sprint3/performance/page-load.md
_private/notes/sprint3/performance/cell-execution.md
_private/notes/sprint3/performance/llm-latency.md
_private/notes/sprint3/performance/auth-dependent.md
_private/notes/sprint3/performance/raw/
```

Key commands:

```bash
cd ui
pnpm build
```

```bash
node -e '<fetch https://jsnb.org/api/v1/health 50 times and write CSV>'
```

```bash
node -e '<fetch https://d2e2ymc27fdfn5.cloudfront.net/api/v1/health 50 times and write CSV>'
```

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless=new \
  --remote-debugging-port=9222 \
  --user-data-dir=/private/tmp/jsnb-perf-chrome \
  --disable-gpu \
  --no-first-run \
  --no-default-browser-check \
  about:blank
```

```bash
cd ui
pnpm vitest run src/features/notebook/runtime/performance.measure.test.ts
```

```bash
PERF_TEST_EMAIL='<test-email>' \
  node <local-private-auth-dependent-script>
```

```bash
node <local-private-auth-browser-script>
```

The Vitest measurement file was temporary and was deleted after recording raw
cell-execution timings.
