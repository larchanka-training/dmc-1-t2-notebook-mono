# Manual test checklist

A hands-on checklist for browser-side verification of a PR. Mirrors
the smoke subset of `docs/qa/autotest-tasks.md` but for human eyes —
use it when Playwright E2E isn't wired yet, or when the autotest
covers only the happy path and you want to feel out edge behaviour
before merge.

**How to use**

1. Boot the local stack: `./start-services.sh`.
2. Open `http://notebook.com` (after the hosts entries from root
   `AGENTS.md` §4 are in place).
3. Walk through the sections **relevant to the PR** — not the whole
   list. Each section maps to a feature area and to numbered
   scenarios in `docs/qa/qa-plan.md` §6.
4. Note any divergence in the PR description (don't silently move on).

---

## Authentication (qa-plan §6.1: A-NN)

- [ ] **Request OTP — happy path** (A-01). Enter a valid email →
      OTP form appears. In dev mode the response body shows the
      OTP code (see `api/docs/auth.md` §6).
- [ ] **Verify OTP — happy path** (A-02). Correct code → JWT issued,
      redirect to dashboard.
- [ ] **Wrong OTP** (A-03). Inline error, OTP not consumed, retry
      works.
- [ ] **Expired OTP** (A-04). After TTL, code is rejected with a
      clear message + "Resend" CTA.
- [ ] **Resend throttle** (A-05). Hammering Resend is blocked with
      countdown.
- [ ] **Protected route without JWT** (A-06). Direct nav to a
      protected URL redirects to login.
- [ ] **Email enumeration** (A-08). Existing vs. non-existent email
      give visually identical UI (no user enumeration).
- [ ] **No password fields anywhere**. The temporary `/auth/login`
      stub (`api/docs/auth.md` §1) must not be exposed in the UI.

## Notebook editor (qa-plan §6.2: E-NN)

- [ ] **Create notebook** (E-01). Empty editor opens, default title
      in sidebar.
- [ ] **Run JS code** (E-02). Output panel shows correct result.
- [ ] **Runtime error in code** (E-03). Error appears in output
      panel; the app does not crash, the editor stays interactive.
- [ ] **Manual save** (E-04). Success toast; reload preserves
      content.
- [ ] **Rename** (E-05). Title updates in editor, sidebar, browser
      tab.
- [ ] **Delete** (E-06). Notebook gone; redirect happens; no zombie
      in sidebar.
- [ ] **Multiple notebooks** (E-07). Switching in sidebar reloads
      editor content correctly; no state leak.

## Code execution / sandbox (qa-plan §6.3: X-NN)

The execution model is QuickJS WASM in a Web Worker (see
`docs/execution-architecture.md`) — **not** an iframe sandbox, despite
older wording in `qa-plan.md`.

- [ ] **`console.log` golden path** (X-01). String reaches output
      panel as text, no JS errors in DevTools console.
- [ ] **Infinite loop** (X-02). Aborted by timeout; UI stays
      responsive (you can click another button); the worker is killed,
      not stuck.
- [ ] **`fetch()`** (X-03). Behaviour matches documented sandbox
      policy. If blocked — clear message, not unhandled exception.
- [ ] **Syntax error** (X-04). Parse error shown **before** execution
      starts (not after).

## Offline / IndexedDB / manual sync (`api/docs/auth.md` §7–8)

- [ ] **Offline create** — disable network in DevTools, create cell,
      reload page. Cell survives (IndexedDB).
- [ ] **Manual sync after reconnect** — re-enable network, trigger
      sync. Local notebook reaches server.
- [ ] **LWW per cell** — edit the same cell on two devices/tabs;
      the cell with the later `updatedAt` wins on next sync.
- [ ] **Delete-vs-edit** — delete cell on tab A while editing on tab B
      offline. After sync, the tab-B edit wins (it has the later
      `updatedAt`); the cell does not stay deleted (`auth.md` §8).
- [ ] **Sync requires auth** — sign-out should disable the sync
      button.

## Sharing (qa-plan §6.4: S-NN)

- [ ] **Generate share link** (S-01). Unique URL, copyable.
- [ ] **Guest opens link** (S-02). Read-only mode; edit/save absent
      or disabled.
- [ ] **Guest runs code** (S-03). Execution works; result is not
      saved to owner's notebook.
- [ ] **Revoke** (S-04). Saved URL stops working; 404 / clear "not
      found" UI.
- [ ] **Deleted notebook** (S-05). Share URL of a deleted notebook
      shows clear empty state, not a JS error.

## LLM code generation (qa-plan §6.6: L-NN)

The chain is **WASM (browser) → backend LLM → OpenAI API** per
`docs/requirements.md` and `qa-plan.md` §5.4.

- [ ] **WASM happy path** (L-01). Code generated client-side, no
      network call to `/llm/generate`.
- [ ] **Fallback to backend** (L-02). WASM cannot handle → request
      hits backend → code returned. User sees no error.
- [ ] **Fallback to OpenAI** (L-03). Backend returns 503 → OpenAI
      path; user notified if UX policy requires.
- [ ] **All tiers fail** (L-04). Clear error; editor untouched;
      Generate button re-enabled.
- [ ] **Empty prompt** (L-05). Generate disabled.
- [ ] **Prompt over limit** (L-06). Counter red, Generate disabled,
      no request sent.
- [ ] **WASM still loading** (L-09). Spinner shown; request queued;
      result inserted automatically when ready.
- [ ] **No WASM in browser** (L-10). Auto-fallback to backend, no
      user-facing error.

## Cross-browser smoke (qa-plan §5.4)

For UI-heavy PRs:

- [ ] **Chromium** — primary; should always work.
- [ ] **Firefox** — at least the smoke flows (auth, create notebook,
      run code).
- [ ] **WebKit / Safari** — same. WASM and sandbox can behave
      differently here.

## Observability (qa-plan §5.5)

- [ ] **Errors are logged**. In api dev mode the structlog JSON line
      shows up in the container log; in ui DevTools the console
      doesn't drown in stack traces.
- [ ] **No secrets in logs / network**. JWT/refresh tokens, LLM keys,
      OTP codes (in prod mode) must not leak into the console,
      network panel, or backend log.

## Cross-link

- `docs/qa/qa-plan.md` — full scenario tables A-NN..L-NN
- `docs/qa/autotest-tasks.md` — Playwright counterpart (when wired)
- `docs/execution-architecture.md` — sandbox details for X-NN
- `api/docs/auth.md` §7–8 — sync + conflict resolution behaviour
- `.agents/skills/notebook-qa/SKILL.md` — process step 4 (manual
  verification)
- `.agents/skills/notebook-pr-review/SKILL.md` — used by reviewers
