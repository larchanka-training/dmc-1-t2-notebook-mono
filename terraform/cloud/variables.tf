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

variable "frontend_acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 for the prod CloudFront distribution. Required when frontend_aliases is non-empty. Empty string or null falls back to the default *.cloudfront.net cert. Default is empty string (not null) so an unset GitHub Actions variable lands here cleanly."
  type        = string
  default     = ""
}

variable "frontend_aliases" {
  description = "Alternate domain names for the prod CloudFront distribution, e.g. [\"jsnb.org\",\"www.jsnb.org\"]. Every entry must be covered by the cert at frontend_acm_certificate_arn."
  type        = list(string)
  default     = []
}
