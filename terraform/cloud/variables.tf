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
