variable "aws_region" {
  description = "AWS region for the preview-cloud shared layer."
  type        = string
  default     = "eu-north-1"
}

variable "project" {
  description = "Resource name prefix for the preview shared layer."
  type        = string
  default     = "jsnotes-t2-preview"
}

# Distinct from prod (10.0.0.0/16) so the two VPCs stay readable side by side.
# They are not peered, so overlap would be harmless, but a separate range is
# clearer.
variable "vpc_cidr" {
  description = "CIDR block for the preview VPC."
  type        = string
  default     = "10.1.0.0/16"
}

variable "app_environment" {
  description = "Non-secret env vars for the shared preview main-api (one key = one env var). APP_ENV is left at the api default (\"dev\") on preview. ENABLE_EXECUTE stays false by default; preview is the only env where it may be flipped to true (the prod hard-guard forbids it). Secrets go through Secrets Manager, not here."
  type        = map(string)
  default = {
    ENABLE_EXECUTE               = "false"
    LLM_CONTEXT_SUMMARY_STRATEGY = "compact-oldest"
    LLM_MAX_PROMPT_BYTES         = "8192"
  }
}
