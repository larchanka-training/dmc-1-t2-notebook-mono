# LLM Rate Limiter Redis/ElastiCache Roadmap

> Follow-up for `larchanka-training/dmc-1-t2-notebook-api#54`.
> Decision as of 2026-06-21: **do not implement Redis/ElastiCache now**.
> The current project scope keeps the process-local MVP limiter and records the
> production-grade path for a future sprint.

## 1. Why This Follow-up Exists

The backend currently protects `POST /api/v1/llm/generate` with a process-local
sliding-window limiter:

```text
20 LLM requests / minute / authenticated user
```

The current implementation lives in the API process memory:

```text
api/app/modules/llm/services/rate_limiter.py
InMemoryRateLimiter
```

That is acceptable for the sprint MVP and for local development, but it is not a
cluster-wide production limiter.

In production, the backend is not conceptually "one computer". It is an ECS
service that can run more than one backend task:

```text
Browser
  -> CloudFront / ALB
  -> ECS service
      -> backend task #1
      -> backend task #2
      -> backend task #3
```

Each backend task is an isolated container with its own process memory. Python
global variables and in-memory dictionaries are not shared between tasks:

```text
backend task #1 RAM != backend task #2 RAM != backend task #3 RAM
```

So with an in-memory limiter, each task has its own counter:

```text
task #1: user A has 10 requests in the current minute
task #2: user A has 8 requests in the current minute
task #3: user A has 7 requests in the current minute
```

No single task sees that the user has made 25 requests in total. The effective
limit becomes:

```text
20 * number_of_backend_tasks
```

This is why a future production-grade limiter needs a shared temporary store.

## 2. Mental Model

Think of the deployed backend as several separate servers behind a request
distributor:

```text
User
  -> request distributor / load balancer
      -> backend server #1
      -> backend server #2
      -> backend server #3
```

The user still sees one site, for example `jsnb.com`, but each HTTP request may
be handled by a different backend task. The user does not create tasks manually;
the infrastructure does:

- ECS desired count;
- autoscaling;
- rolling deploys;
- high-availability placement.

Long-lived data already goes into a shared database:

```text
PostgreSQL:
  users
  notebooks
  sessions
  refresh tokens
```

Rate-limit counters are different. They are short-lived operational data:

```text
Redis / Valkey:
  user_id -> request timestamps for the last 60 seconds
```

If these counters disappear, notebooks and users are not lost. The limiter just
starts a fresh time window.

## 3. Redis, Valkey, and ElastiCache

### Redis

Redis is a fast in-memory key-value database. It is commonly used as shared
temporary state for backend clusters:

- rate limiting;
- cache;
- distributed locks;
- short-lived counters;
- queues / pub-sub in some architectures.

For the LLM limiter, Redis would store only recent request timestamps, not
business records:

```text
llm:rate:user:<user_id> -> timestamps in the current sliding window
```

### Valkey

Valkey is a Redis-compatible fork. AWS supports ElastiCache for Valkey and
prices it lower than ElastiCache for Redis OSS in the checked region. For this
project's limiter, Valkey should be functionally sufficient if the team accepts
Redis-compatible storage rather than Redis OSS specifically.

The future implementation must explicitly choose one engine:

- **Redis OSS** when familiarity and exact Redis naming matter most;
- **Valkey** when lower cost and Redis compatibility are acceptable.

### ElastiCache

ElastiCache is AWS-managed Redis/Valkey/Memcached. Instead of running Redis
manually on EC2, AWS manages the cache service:

- cache creation;
- endpoint management;
- VPC placement;
- patching and maintenance;
- monitoring integration;
- scaling options, depending on the chosen mode.

The API would connect through a private endpoint:

```text
API ECS task -> REDIS_URL -> ElastiCache endpoint
```

## 4. Deployment Models

There are two relevant deployment models.

### Provisioned Node

With a provisioned node, the team chooses an instance type, for example
`cache.t4g.micro`.

Properties:

- predictable hourly price;
- simple to reason about;
- capacity is fixed until changed;
- high availability requires extra nodes / replication configuration.

Example:

```text
ElastiCache Redis OSS cache.t4g.micro
or
ElastiCache Valkey cache.t4g.micro
```

### Serverless

With ElastiCache Serverless, AWS manages more of the capacity model. Pricing is
based on stored data and request processing units.

Properties:

- less capacity planning;
- easier for spiky traffic;
- pricing has minimum metered storage;
- request cost is metered through ECPUs.

For small rate-limit data, minimum storage dominates the cost.

## 5. Sliding-Window Algorithm

The existing controller contract should stay unchanged:

```python
check(user_id) -> retry_after_seconds | None
```

Meaning:

```text
None -> request is allowed
int  -> request is blocked; return Retry-After with that many seconds
```

A Redis/Valkey implementation can use a sorted set:

```text
key   = llm:rate:user:<user_id>
score = unix timestamp of the request
value = unique request id
```

Algorithm:

```text
1. Remove timestamps older than the window.
   ZREMRANGEBYSCORE key 0 now-window

2. Count timestamps in the current window.
   ZCOUNT key now-window now

3. If count >= limit:
     return retry_after

4. Otherwise:
     ZADD key now request_id
     EXPIRE key window
     return None
```

The future implementation should run this atomically, preferably through a Redis
Lua script, so concurrent requests cannot slip between the `count` and `add`
steps.

## 6. Failure Policy

The team must choose how the API behaves when Redis/Valkey is unavailable.

### Fail Open

```text
Redis unavailable -> log warning -> allow the LLM request
```

Advantages:

- LLM generation keeps working during cache outages;
- better user experience;
- acceptable when rate-limit state is protective, not business-critical.

Disadvantages:

- temporary loss of rate limiting;
- higher risk of Bedrock cost spikes during a cache outage.

### Fail Closed

```text
Redis unavailable -> return 503 -> block the LLM request
```

Advantages:

- cost-control stays strict;
- abuse does not bypass the limiter.

Disadvantages:

- Redis/Valkey becomes a hard dependency for LLM generation;
- cache outage breaks the feature for all users.

Recommended future policy for this educational project:

```text
fail-open
```

Reason: losing rate-limit counters does not corrupt user data. For this project,
temporary degraded cost-control is preferable to making LLM generation fail
whenever Redis/Valkey is unavailable. A production SaaS with strict cost limits
may choose fail-closed instead.

## 7. Cost Estimate

Pricing was checked on 2026-06-21 for AWS region `eu-north-1` / EU Stockholm.

Sources:

- AWS ElastiCache pricing page:
  `https://aws.amazon.com/elasticache/pricing/`
- AWS public price list for `AmazonElastiCache`, region `eu-north-1`:
  `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonElastiCache/current/eu-north-1/index.json`

This is an estimate, not a billing guarantee. Re-check with AWS Pricing
Calculator before implementing the infrastructure.

### Redis OSS `cache.t4g.micro`

```text
Price: $0.020/hour
Monthly estimate: 0.020 * 730h = $14.60/month
```

With two nodes:

```text
2 * $14.60 = $29.20/month
```

### Valkey `cache.t4g.micro`

```text
Price: $0.016/hour
Monthly estimate: 0.016 * 730h = $11.68/month
```

With two nodes:

```text
2 * $11.68 = $23.36/month
```

### Redis OSS Serverless

```text
Storage price: $0.133/GB-hour
Minimum metered storage: 1 GB
ECPU price: $0.0036 per million ECPUs
```

Minimum monthly estimate:

```text
0.133 * 1 GB * 730h = $97.09/month
```

For this small limiter, request cost is expected to be tiny compared to the
minimum storage floor.

### Valkey Serverless

```text
Storage price: $0.089/GB-hour
Minimum metered storage: 100 MB
ECPU price: $0.0024 per million ECPUs
```

Minimum monthly estimate:

```text
0.089 * 0.1 GB * 730h = $6.50/month
```

Request cost should be small for the project's expected traffic, but it is still
usage-based.

### Cost Summary

| Option | Approximate monthly cost | Notes |
|---|---:|---|
| Redis OSS `cache.t4g.micro`, 1 node | `$14.60` | Simple and familiar; no HA |
| Redis OSS `cache.t4g.micro`, 2 nodes | `$29.20` | Better availability; higher cost |
| Valkey `cache.t4g.micro`, 1 node | `$11.68` | Redis-compatible; cheaper |
| Valkey `cache.t4g.micro`, 2 nodes | `$23.36` | Cheaper multi-node option |
| Redis OSS Serverless | `$97.09+` | Expensive minimum for this use case |
| Valkey Serverless | `$6.50+` | Cheapest-looking option; requires Valkey approval |

## 8. Option Comparison

| Criterion | Redis OSS node | Valkey node | Redis OSS Serverless | Valkey Serverless |
|---|---:|---:|---:|---:|
| Works for LLM rate limiting | Yes | Yes | Yes | Yes |
| Shared state across API tasks | Yes | Yes | Yes | Yes |
| Sorted set support | Yes | Yes, Redis-compatible | Yes | Yes, Redis-compatible |
| Requires choosing instance size | Yes | Yes | No | No |
| Lowest small-workload cost | Medium | Medium-low | High | Low |
| Most familiar to the team | High | Medium | High | Medium |
| Serverless scaling | No | No | Yes | Yes |
| Good fit for educational budget | Yes | Yes | Usually no | Yes |
| Requires Valkey approval | No | Yes | No | Yes |

## 9. Recommendation

Do not implement Redis/ElastiCache in the current sprint. It is useful
production knowledge, but it adds:

- a new runtime dependency;
- a new AWS service;
- Terraform changes;
- ECS security group and environment wiring;
- failure-policy decisions;
- ongoing monthly cost.

For the future implementation, prefer one of these two options:

### Cost-Conscious Classic Option

```text
Engine: Redis OSS or Valkey
Mode: provisioned cache.t4g.micro
Failure policy: fail-open
Local development: keep InMemoryRateLimiter
```

Choose Redis OSS if familiarity matters more than price. Choose Valkey if the
team accepts Redis compatibility and wants a lower bill.

### Cheapest Serverless-Looking Option

```text
Engine: Valkey
Mode: Serverless
Failure policy: fail-open
Local development: keep InMemoryRateLimiter
```

This has the best listed minimum cost, but should be validated against Terraform
support, regional availability, and actual billing before implementation.

Avoid Redis OSS Serverless for this project unless the team explicitly accepts
the approximately `$97/month` minimum.

## 10. Future Implementation Roadmap

### Phase 0 — Decision

Agree on:

- Redis OSS vs Valkey;
- provisioned node vs serverless;
- fail-open vs fail-closed;
- one node vs multi-node / high availability;
- whether preview and production both get the cache;
- whether local development keeps in-memory fallback.

### Phase 1 — API Code

Repository: `dmc-1-t2-notebook-api`

Suggested scope:

- add a Redis/Valkey client dependency;
- introduce a small `RateLimiter` protocol;
- keep `InMemoryRateLimiter` for tests and local fallback;
- add `RedisRateLimiter`;
- implement sliding-window logic with sorted sets and an atomic Lua script;
- add settings:
  - `LLM_RATE_LIMIT_BACKEND=inmemory|redis`
  - `LLM_RATE_LIMIT_REDIS_URL`
  - `LLM_RATE_LIMIT_FAILURE_POLICY=fail_open|fail_closed`
- keep the controller contract unchanged:
  - allowed -> `None`
  - limited -> `retry_after_seconds`
- add tests:
  - request allowed;
  - request limited;
  - retry-after is calculated;
  - old timestamps are evicted;
  - Redis unavailable with fail-open;
  - Redis unavailable with fail-closed.

### Phase 2 — Infrastructure

Repository: `dmc-1-t2-notebook-mono`

Suggested scope:

- add ElastiCache/Valkey Terraform resource;
- place it in private subnets;
- add a security group rule:

```text
API ECS task security group -> cache security group, port 6379
```

- pass the cache endpoint into the API ECS task definition;
- update preview/prod variables if both environments are included;
- document how to disable or replace the cache.

### Phase 3 — Documentation and Runbook

Update:

- `docs/aws-cloud-migration.md` for the cloud architecture;
- `docs/ai-architecture.md` for LLM rate-limit behavior;
- `docs/sprint-3-deliverables/DevOps-runbook.md` for Redis/Valkey outage handling;
- `AGENTS.md` if the deployment map changes materially.

Runbook should include:

- how to recognize cache outage;
- expected behavior under fail-open/fail-closed;
- CloudWatch metrics/log queries;
- rollback path to in-memory fallback if needed.

### Phase 4 — Verification

Required checks:

- API unit tests;
- local integration test against a Redis container, if practical;
- Terraform plan for preview/prod;
- deploy to preview;
- manual test:

```text
Run >20 LLM requests/min/user across scaled API tasks.
Expected: shared 429 after the global limit, not per-task limit.
```

## 11. Current Decision

The team decided not to implement this now because the added cost and
infrastructure complexity are disproportionate for the current educational
stage.

This document is the accepted deliverable for the follow-up: it explains the
problem, the AWS options, approximate cost, and a future implementation path.

