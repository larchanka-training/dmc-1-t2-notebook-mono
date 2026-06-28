# Engineer #5 — Demo Day Outline

> Source of truth for the live deck, charts and numbers:
> `.agents/issues/TARDIS-156/presentation-app/` (Vue 3 + Vite, custom slide
> engine, D3/SVG charts) and its plan `.agents/issues/TARDIS-156/final-presentation-plan.md`.
> All figures live in one place — `presentation-app/src/data/metrics.js` — and
> are reconciled with the Sprint 3 reports before the show.

## Objective

Deliver a 15–20 minute launch presentation for JS Notebook that tells one
story (problem → architecture → decisions → honest problems → quality →
metrics → cost → recovery → security → lessons → roadmap), and ends with a
**live demo of the real product** as the climax.

Narrative principle: lead the audience through a single story, not a list of
technologies. Every heavy (chart) part rises from the bottom with an elastic
fill and leaves with the signature "drop-away" fall — the visual leitmotif of
the whole deck.

## Audience

- Course reviewers / committee (Modern Software Development course, team T2).
- Technically literate: CI/CD, AWS, preview-per-PR and the architecture are
  "wow" points worth showing, not over-explaining.

## Timebox

- Total duration: 15–20 min.
- Demo duration: 4–5 min (the climax — do not cut it).
- Q&A buffer: remaining time after the deck.

Rough budget: cover + problem ~2 min · architecture + decisions ~4 min ·
problems→fixes + QA ~3 min · performance + cost ~3–4 min · DR + security
~2 min · lessons + roadmap ~2 min · live demo 4–5 min · Q&A the rest.
Advice: do not spend 10 minutes on the architecture diagram — the demo and the
lessons matter more.

## Presentation Structure

Slide order and entrance transitions are defined in
`presentation-app/src/data/slides.js`.

### 1. Introduction

- What JS Notebook is: a browser-based JS/TS notebook with offline-first
  storage and AI code generation.
- Why it matters: code + markdown in one place, instant run, local storage,
  background sync, AI hints.
- Team / sprint context: team T2, Sprint 3 (release sprint). Roles (Tech Lead /
  QA / DevOps / Engineers) rotated every sprint — almost everyone wore several
  hats; 7 people active (cover slide `S00Cover`, team slide `S13Team`).
- Hero fact for the cover/closing: **the first bottleneck was not the backend
  — it was the cold delivery of 7.93 MB of JavaScript.**

### 2. Architecture

- One screen, not ten minutes. Animated SVG node-and-flow diagram
  (`S02Architecture`).
- Frontend: React 19 SPA on CloudFront + S3.
- Backend: FastAPI on ECS, PostgreSQL on RDS, behind an ALB.
- Execution model: QuickJS / WASM in a Web Worker (browser path is the MVP).
- Cloud infrastructure: AWS eu-north-1 (ECS / RDS / S3 / CloudFront), Bedrock
  for cloud AI. Highlighted AI route `Browser → backend → Bedrock` — **no keys
  in the browser** (LLM goes through the backend proxy via an IAM role).
- Storage: local-first — IndexedDB with background autosync.

### 3. Problems

- User pain the product solves: code + markdown together, instant run, local
  storage, background sync, AI assistance (slide `S01Problem`).
- Engineering constraints: educational SaaS on a shared course account —
  production quality of execution, educational scope of ambition (deliberate
  trade-offs such as bare HTTP at the ALB, default CloudFront cert, single
  `production` environment).
- Honest "problems → fixes" (slide `S04Problems`, six real incidents):
  - production ECS rollback from missing/placeholder `JWT_SECRET` /
    `OTP_HASH_SECRET` → start-time secret validation;
  - `ui` `main` was unprotected (direct push without review) → branch
    protection (PR + required review);
  - Bedrock region/model/IAM friction → moved to a task IAM role;
  - preview PR-number drift (UI vs API) → process + docs;
  - docs drift (JSON REST vs a "future" SSE) → contract sync;
  - OTP abuse: race on the `count + insert` rate-limit, burn-the-OTP trade-off
    → documented as a known limitation.

### 4. Solutions

- Five key engineering decisions (slide `S03Decisions`):
  - local-first (IndexedDB + background sync);
  - in-browser execution (QuickJS/WASM in a Web Worker);
  - passwordless email-OTP → JWT;
  - in-browser AI (WebLLM) vs cloud AI (Bedrock through a backend proxy — no
    keys in the browser, generated code is a suggestion, not auto-run);
  - AWS deploy (ECS / RDS / S3 / CloudFront).
- CI/CD as a strength: GitHub Actions, immutable ECR images, auto-deploy on
  merge to `main`, preview-per-PR.
- Observability & privacy: CloudWatch metadata-only logging (no code, prompts
  or tokens in logs); Bedrock via an IAM role (no stealable key).

### 5. Mistakes

- What went wrong and what we learned (slides `S04Problems`, `S10Lessons`):
  - secrets not validated at startup caused a real production rollback;
  - the `main` branch was initially unprotected;
  - Bedrock setup (region/model/IAM) took several iterations;
  - observability and analytics arrived later than they should have.
- What changed afterward: secret validation on boot, branch protection,
  IAM-role Bedrock access, CloudWatch analytics + alarms.

### 6. Metrics

All numbers from the Sprint 3 reports, held in
`presentation-app/src/data/metrics.js` (slides `S05Quality`, `S06Performance`,
`S07Cost`).

- Performance: production health p95 `197.67 ms` (50/50 success); authenticated
  notebook list/get p95 `193.40 / 191.04 ms`; notebook patch p95 `786.81 ms`
  (caveat: 10 samples); cloud LLM p95 `1 579.72 ms` (`nova-lite`, 3/3); QuickJS
  warm reduce p95 `1.56 ms`.
- Cold load (the bottleneck): cold FCP `4 856 ms`, cold transfer `8.13 MiB`,
  main production JS `~7.93 MB` (no gzip/brotli); target page load `< 2.5 s`.
- Cost (per month, prod + always-on preview): roughly fixed `~$80–140` plus
  variable Bedrock/traffic scaling with users (100 / 1 000 / 10 000).
- Quality / release: regression coverage across Auth, Notebook CRUD+sync,
  Execution, AI, UI, deploy smoke; security findings (XSS, JWT, API authz,
  sandbox, prompt injection) reviewed and mitigated; release decision
  **Go (with accepted caveats)**.
- Models: generator `eu.amazon.nova-lite-v1:0`, guard `eu.amazon.nova-micro-v1:0`.

### 7. What Worked Best

- Strongest parts of the system (slide `S10Lessons`, "worked best" column):
  - local-first UX;
  - in-browser execution;
  - production AWS deploy;
  - Bedrock without an API key (IAM role);
  - preview-per-PR infrastructure;
  - contract/docs discipline.

### 8. What We Would Redesign

- Architecture / process changes (slide `S10Lessons`, "would redo" column):
  - introduce observability earlier;
  - add product analytics from day one;
  - per-PR DB isolation;
  - decide on streaming LLM earlier;
  - run security and performance audits earlier.

### 9. Demo Flow

- Scenario (slide `S12Demo`, 12 steps): login (email OTP) → create notebook →
  markdown cell → code cell → **Run** (QuickJS) → AI generation (browser/cloud)
  → manual sync; show stdout / result / error.
- Key user journey: from empty notebook to a running cell with AI-assisted code
  in under a minute.
- Behavior: the slide shows a friendly face with cursor-tracking eyes; clicking
  it opens the product (`urls.prod` = `https://jsnb.org`) in a new adjacent
  active tab (`window.open(url, '_blank', 'noopener')`) — no iframe.
- Fallback plan if the live demo fails: keep a pre-recorded screencast of the
  demo in a separate tab and switch to it.

### 10. Closing

- Final message: restate the hero fact ("the first bottleneck was the cold
  7.93 MB JS, not the backend") and the live URL `https://jsnb.org`
  (slide `S13Closing`).
- Next steps: the 3-month roadmap (slide `S11Roadmap`) — P0 release blockers,
  P1 reliability, P2/P3 features.
- Team credits (slide `S13Team`): avatars by contribution, one line that roles
  rotated each sprint.

## Slide Checklist

- [ ] `S00Cover` — title + hero subtitle + project-composition donut.
- [ ] `S01Problem` — pain → solution cards.
- [ ] `S02Architecture` — animated node/flow diagram, AI route highlighted.
- [ ] `S03Decisions` — five decisions stepper + in-browser-vs-cloud split.
- [ ] `S04Problems` — six real incident cards (spotlight, keys ↓/↑).
- [ ] `S05Quality` — coverage gauges + severity grid + Go/No-Go card.
- [ ] `S06Performance` — bundle donut + cold-transfer bars + latency + KPIs.
- [ ] `S07Cost` — cost-at-scale + cost-structure donut + break-even.
- [ ] `S08Recovery` — 7 DR scenarios + runbook metrics.
- [ ] `S09Security` — severity matrix + mitigations.
- [ ] `S10Lessons` — "worked best" / "would redo" two columns.
- [ ] `S11Roadmap` — P0/P1/P2–P3 timeline.
- [ ] `S12Demo` — live product (face → opens `https://jsnb.org`).
- [ ] `S13Team` — contributor grid with speaker teleprompter (`N`).
- [ ] `S13Closing` — hero fact + live URL + Q&A.

## Demo Checklist

- [ ] Numbers in `metrics.js` reconciled with the final Sprint 3 reports
      (`E3-performance-report.md`, `E2-cost-analysis.md`, `QA-release-report.md`,
      `E4-security-review.md`).
- [ ] Pre-recorded demo screencast ready as a fallback tab.
- [ ] Rehearsed on the show display/resolution (16:9, ≥ 1280×720).
- [ ] Hotkeys verified: `→/Space` next, `←` prev, `F` fullscreen, `D`
      demo-mode, `N` presenter window.
- [ ] Go/No-Go matches the final `QA-release-report.md` (do not promise
      readiness if QA/Security is No-Go).
- [ ] Offline build (`npm run build` → `dist/`) on a USB stick in case there is
      no internet.
- [ ] `https://jsnb.org` reachable (and the preview URL as a backup).

## Speaker Notes

- Presenter notes are **not** rendered over the slide (they would be visible
  when sharing the screen). Press `N` to open the presenter window
  (`#/presenter`); keep it on your own screen and share only the deck tab.
- Per-slide notes are registered by `SpeakerNotes.vue` and pushed to the
  presenter window via `postMessage` (`src/presenter.js`). The connection dot
  turns green when notes are arriving.
- Slide-specific teleprompter text lives next to each slide:
  `S02Architecture.vue` (what talks to what, why AI goes through the backend),
  `S04Problems.vue` / `S08Recovery.vue` / `S09Security.vue` / `S10Lessons.vue`
  / `S11Roadmap.vue` (`note`/`detail` fields), `S12Demo.vue` (`demoNotes`,
  12-step demo script), `S13Team.vue` (per-person contribution from
  `src/data/team.js`).
- Demo discipline: open the product in the adjacent tab, run the 12-step
  scenario, then return to the deck tab for Q&A. If the live demo breaks,
  switch to the recorded screencast.
