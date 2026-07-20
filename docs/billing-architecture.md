# Billing & Paid Subscriptions — Research / Decision Record

> **Status: research / proposal (2026-07-05).** Nothing in this document is
> implemented yet. It records the feasibility analysis, the recommended
> architecture, and a phased plan for adding a paid subscription tier to
> JS Notebook — primarily to unlock more capable (more expensive) cloud AI
> models via OpenRouter. When implementation lands, this document becomes the
> billing architecture reference and must be kept in sync with the code (§9 of
> `AGENTS.md`).

---

## 1. Motivation

Two forces converge on the same change:

1. **Product:** a paid tier ("pro") that unlocks premium features — most
   valuably, access to stronger cloud models (Claude, GPT-class) for the
   AI code-generation feature, higher rate limits, and larger usage quotas,
   while "free" keeps the in-browser WebLLM path plus a cheap backend model.
2. **Infrastructure:** the project is migrating off AWS. The current backend
   LLM path uses Amazon Bedrock through a VPC interface endpoint and a task
   IAM role (`docs/ai-architecture.md` §6, `terraform/modules/backend/bedrock.tf`)
   — neither exists off-AWS. After the migration the backend generation tier
   loses its provider unless we switch to a hosting-agnostic one. OpenRouter
   (plain HTTPS + API key) solves that regardless of billing.

So the OpenRouter adapter is needed anyway; the billing work builds on top of
it rather than being a separate track.

## 2. Current-state assessment (what the codebase already gives us)

| Aspect | State |
|---|---|
| LLM provider abstraction | ✅ `LlmProvider` Protocol (`api/app/modules/llm/services/generation_service.py`, `converse(model_id, …)`); `BedrockClient` is just one implementation, injected in `build_generation_service()` |
| Model selection | ✅ config-only: `llm_bedrock_guard_model_id` / `llm_bedrock_generator_model_id` (`api/app/core/config.py`) — no model IDs hardcoded in logic |
| Rate limiting | ⚠️ in-memory sliding window, flat 20 req/min per user (`rate_limiter.py`); no cost/token awareness. Redis upgrade path already designed in `docs/llm-rate-limiter-redis-roadmap.md` (deferred) |
| `User` model | ❌ `id, email, display_name, created_at` only — no plan/tier/role fields (`api/app/modules/auth/models/user.py`) |
| JWT claims | ❌ `sub, sessionId, iat, exp` only — no plan claim |
| DB schema | ❌ no billing tables (changelogs 0001–0006 + ai-context) |
| Account UI | ❌ no profile/subscription page; LLM errors keyed on `error.code` + `tier` |
| Payment gateway | ❌ none |

**Conclusion:** the LLM pipeline is clean and provider-agnostic — an
OpenRouter adapter fits behind the existing Protocol without breaking the
contract. Everything billing-specific (plans, quotas, payments, UI) is
greenfield.

## 3. Why OpenRouter

- One OpenAI-compatible API over 315+ models (Anthropic, OpenAI, Google,
  DeepSeek, Meta, …), one key, one prepaid credit balance. Platform fee is
  ~5.5% on credit purchases (min $0.80).
- **Management / Provisioning API** (`/api/v1/keys`): keys can be created
  programmatically per user or per tier, each with its own spend limit
  (optionally resetting daily/weekly/monthly); OpenRouter meters usage per
  key. This removes the need to build our own token metering for the MVP
  cost ceiling.
- Works from any hosting (plain HTTPS + API key) — compatible with the
  post-AWS environment, unlike Bedrock.
- Cheap models (Gemini Flash, DeepSeek, Llama, `:free` variants) cover the
  free tier at Nova-Micro/Lite-like cost; premium models (Claude
  Sonnet/Opus, GPT-5-class) become the paid-tier feature.

**Risks:** single point of failure and the ~5.5% margin. Mitigations later:
BYOK (route through direct provider keys via OpenRouter) or an alternative
aggregator (e.g. Together.ai). The `LlmProvider` Protocol keeps that swap
cheap.

## 4. Payment provider

| Option | Fits when | Notes |
|---|---|---|
| **Stripe, test mode** *(recommended for the educational scope)* | Full subscription lifecycle without real money | Best DX; Stripe Billing gives subscriptions, webhooks, Customer Portal out of the box. Live mode is not available to RF entities |
| Paddle / Lemon Squeezy (merchant of record) | Real international sales | ~5% + $0.50; they own tax/compliance; Lemon Squeezy is the fastest to launch |
| YooKassa / CloudPayments | Real sales in the RF market | Recurring payments supported; no Stripe-grade subscription engine — more hand-rolled logic |

**Decision:** isolate the payment provider behind our own `PaymentProvider`
interface (mirroring the `LlmProvider` Protocol pattern) and implement
**Stripe test mode** in the MVP. The live-provider choice (MoR vs YooKassa)
is deferred until the target market is decided. Running test-mode-only is a
deliberate, documented educational-scope trade-off (`AGENTS.md` §1).

## 5. Target architecture

### 5.1 Plans (initial)

| Plan | LLM access | Rate limit | Quota |
|---|---|---|---|
| `free` | WebLLM (T1) + backend with a cheap model | 20 req/min | monthly token quota |
| `pro` | Premium models via OpenRouter, model selector in UI | higher | larger quota |

### 5.2 Schema (Liquibase, `api/liquibase/changelog/00xx-billing.xml`)

- `subscription_plans(id, code, name, llm_model_id, rate_limit_per_minute, monthly_token_quota, price_cents, …)`
- `user_subscriptions(id, user_id FK, plan_id FK, status, provider, provider_subscription_id, current_period_start, current_period_end)`
- `payment_events(id, user_id, provider, event_type, payload jsonb, created_at)` — webhook journal, idempotency by provider event id
- `llm_usage(id, user_id, date, request_count, prompt_tokens, completion_tokens, cost_microusd)` — our own usage ledger (kept even with OpenRouter-side metering, for the UI and analytics)

### 5.3 Backend — new module `api/app/modules/billing/{controllers,services,schemas}/`

- Endpoints: `GET /api/v1/billing/plans`, `GET /api/v1/billing/subscription`,
  `POST /api/v1/billing/checkout` (creates a Stripe Checkout Session),
  `POST /api/v1/billing/webhook` (signature verification + idempotency).
- **Entitlements service:** `get_user_plan(user_id) -> PlanEntitlements`
  (model id, rate limit, quota) — consumed by the LLM pipeline.
- **Plan is not put into the JWT.** Access tokens outlive plan changes;
  upgrades/downgrades must apply immediately. The plan is resolved from the
  DB by `sub` with a short in-memory cache — consistent with the fail-open
  philosophy of the current rate limiter.
- `OpenRouterClient` implements the existing `LlmProvider` Protocol;
  `model_id` comes from entitlements instead of a single global config value.
  Provider selection via env `LLM_PROVIDER=bedrock|openrouter` (Bedrock stays
  until the AWS teardown completes).
- Rate limiter reads its limit from entitlements instead of the flat
  `llm_rate_limit_per_minute` constant.
- Secrets (server-side only, per `AGENTS.md` §11): `OPENROUTER_API_KEY`
  (+ provisioning key), `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.

### 5.4 Frontend (`ui/`)

- Subscription page: current plan, usage, Upgrade → Stripe Checkout
  redirect, Customer Portal link for cancellation.
- Model selector in the prompt cell for `pro` (options come from
  entitlements).
- New LLM error `402 quota_exceeded` → "Upgrade" CTA (extends the existing
  `error.code`-keyed handling).
- OpenAPI: notebook domain via `pnpm api:vendor && pnpm api:generate`;
  billing gets its own `ui/openapi/billing.openapi.yaml`, following the
  auth/llm pattern.

### 5.5 Docs to touch during implementation

`docs/ai-architecture.md` §6/§9 (OpenRouter as provider; closes the
"Bedrock cost ceiling" open question), `docs/requirements.md`, and this
document (status flip from proposal to reference).

## 6. Phased plan (each phase = its own api+ui+mono PR set)

1. **P1 — Plans & entitlements (no money):** `subscription_plans` +
   `user_subscriptions` tables, entitlements service, plan-aware rate limit;
   all existing users get `free`. Immediate value: managed quotas.
2. **P2 — OpenRouter adapter:** `OpenRouterClient` behind `LlmProvider`,
   `LLM_PROVIDER` switch, model from entitlements; the guard model also moves
   to OpenRouter. Also unblocks the off-AWS migration (Bedrock replacement).
3. **P3 — Usage metering:** persist `llm_usage` from the response envelope
   (`tokens` is already returned), monthly quota enforcement,
   `quota_exceeded` error.
4. **P4 — Payments:** Stripe test mode (Checkout + webhooks + Customer
   Portal) behind the `PaymentProvider` interface; subscription page in UI.
5. **P5 — later:** live payment provider per target market
   (YooKassa/Paddle), Redis-backed limiter when scaling out (roadmap doc
   exists), BYOK.

P2 is worth doing first/independently — the migration needs it regardless of
billing.

## 7. Risks & constraints

- **Financial:** premium models without a hard monthly cap can burn the
  budget → spend limits on OpenRouter provisioning keys + **fail-closed**
  quota enforcement (deliberately stricter than the fail-open rate limiter).
- **Legal:** real payments imply offer terms, taxes, refunds; educational
  scope stays on test mode (documented trade-off).
- **Webhooks:** require a public HTTPS endpoint — the Cloudflare TLS/domain
  step of the hosting migration is a prerequisite for P4.
- **Process-local rate limiter:** with >1 backend instance, DB-backed quotas
  become the only honest limiter — acceptable at current scale.

## 8. References

- OpenRouter: [FAQ](https://openrouter.ai/docs/faq),
  [Pricing](https://openrouter.ai/pricing),
  [Provisioning API keys](https://openrouter.ai/docs/features/provisioning-api-keys),
  [Per-user keys with spend limits](https://openrouter.zendesk.com/hc/en-us/articles/51680687417499)
- Payments: [Stripe vs Paddle vs Lemon Squeezy (2026)](https://f3fundit.com/stripe-vs-paddle-vs-lemon-squeezy-micro-saas-2026/),
  [MoR comparison](https://fintechspecs.com/blog/stripe-vs-paddle-vs-lemon-squeezy-vs-polar-merchant-of-record-b2b-saas/)
- Internal: `docs/ai-architecture.md`, `docs/llm-rate-limiter-redis-roadmap.md`
