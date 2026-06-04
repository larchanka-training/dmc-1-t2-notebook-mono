variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "aws_region" {
  description = "AWS region (used for the awslogs log driver)."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID (for the ALB target group)."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the ECS tasks."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group for the ALB."
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group for the ECS tasks."
  type        = string
}

variable "ecr_registry" {
  description = "ECR registry host."
  type        = string
  default     = "867633231218.dkr.ecr.eu-north-1.amazonaws.com"
}

variable "ecr_repository" {
  description = "ECR repository name (images tagged api-<tag> / ui-<tag>)."
  type        = string
  default     = "jsnotes-t2"
}

variable "image_tag" {
  description = "Image tag without the api-/ui- prefix. Use an immutable sha-<short> for real deploys; the deploy pipeline overrides this per release."
  type        = string
  default     = "latest"
}

variable "api_port" {
  description = "Container port the API listens on."
  type        = number
  default     = 8000
}

variable "app_environment" {
  description = <<-EOT
    Non-secret environment variables for the API container, rendered into the
    task definition's `environment` block (one key = one env var). Add new
    non-secret config here (LOG_LEVEL, CORS_*, feature flags, …). Secrets do NOT
    go here — use Secrets Manager via the `secrets` block.

    APP_ENV is required and validated: "production" (the default) disables the
    dev-only placeholder X-User-Id auth — protected endpoints return
    501 AUTH_NOT_IMPLEMENTED until real OTP/JWT lands. Do NOT set APP_ENV="dev"
    on a publicly reachable deployment: dev mode authenticates any caller under
    an arbitrary UUID. See the api auth/dependencies.py gate.
  EOT
  type        = map(string)
  default     = { APP_ENV = "production" }

  validation {
    # APP_ENV must be present and a known value — a missing/garbage APP_ENV would
    # silently fall back to the api default ("dev") and re-open the auth hole.
    condition = contains(
      ["production", "staging", "dev", "test", "local"],
      lookup(var.app_environment, "APP_ENV", "")
    )
    error_message = "app_environment must include APP_ENV set to one of: production, staging, dev, test, local."
  }
}

variable "api_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Number of API tasks. Kept at 0 until RDS exists (Phase 3); raise to 1+ afterwards."
  type        = number
  default     = 0
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the API task."
  type        = number
  default     = 14
}
