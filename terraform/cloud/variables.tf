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
  description = "Non-secret env vars for the prod API container (one key = one env var). APP_ENV is kept at \"production\" so the dev-only placeholder auth stays disabled on the public CloudFront URL. Secrets go through Secrets Manager, not here."
  type        = map(string)
  default     = { APP_ENV = "production" }
}

variable "api_desired_count" {
  description = "Number of API tasks. 1 now that the database exists (Phase 3)."
  type        = number
  default     = 1
}

variable "cost_alert_email" {
  description = <<-EOT
    Email subscriber for the Bedrock monthly cost-budget alert. Empty (default) =
    the budget is NOT created — set TF_VAR_cost_alert_email (a CI/repo variable or
    a local tfvars value) to enable it. Kept out of the repo so a personal/team
    address is never committed to this public repository.

    NOTE: on the shared course account the `Service = Amazon Bedrock` filter sums
    ALL teams' Bedrock spend, so treat the threshold as an account-wide early
    warning, not a T2-only figure.
  EOT
  type        = string
  default     = ""
}

variable "cost_alert_budget_usd" {
  description = "Monthly USD threshold for the Bedrock cost budget (alert fires at 80% ACTUAL). Account-wide on the shared account — size accordingly."
  type        = string
  default     = "20"
}
