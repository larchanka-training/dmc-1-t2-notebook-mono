variable "aws_region" {
  description = "AWS region for the cloud-native stack."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Resource name prefix."
  type        = string
  default     = "jsnotes-t2"
}

variable "image_tag" {
  description = "API/UI image tag without the api-/ui- prefix. Immutable sha-<short> for real deploys; the deploy pipeline overrides it per release."
  type        = string
  default     = "latest"
}

variable "app_environment" {
  description = "Non-secret env vars for the prod API container (one key = one env var). APP_ENV is kept at \"production\" so the dev-only placeholder auth stays disabled on the public CloudFront URL. ENABLE_EXECUTE stays false (the API hard-refuses to start with it true in a production-like APP_ENV). Secrets go through Secrets Manager, not here."
  type        = map(string)
  default = {
    APP_ENV = "production"

    # Backend code-execution endpoint (POST /api/v1/execute): a debug/fallback
    # subprocess runner, NOT a production sandbox (docs/execution-architecture.md
    # §12). Set explicitly to false — and it can only ever be false in prod: the
    # API hard-refuses to start with ENABLE_EXECUTE=true in a production-like
    # APP_ENV. EXECUTE_* tuning vars are omitted; the app's defaults are fine.
    ENABLE_EXECUTE = "false"

    # AI-context summary knobs (docs/context-ai-workflow.md §5.1, §6). Plain
    # config flags, not secrets — same class as the above. Set to the app
    # defaults so they are visible/tunable from the task-def; override only to
    # change behaviour (e.g. the "llm" roll-up strategy).
    LLM_CONTEXT_SUMMARY_STRATEGY = "compact-oldest"
    LLM_MAX_PROMPT_BYTES         = "8192"
  }
}

variable "api_desired_count" {
  description = "Number of API tasks. 1 now that the database exists (Phase 3)."
  type        = number
  default     = 1
}
