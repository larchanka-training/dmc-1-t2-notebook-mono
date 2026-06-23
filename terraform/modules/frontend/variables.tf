variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name of the API ALB (CloudFront origin for /api/v1/*)."
  type        = string
}

variable "price_class" {
  description = "CloudFront price class (PriceClass_100 = NA + EU, cheapest)."
  type        = string
  default     = "PriceClass_100"
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the custom-domain TLS. Must live in us-east-1 (CloudFront requirement) and cover every name in aliases. When null, the distribution falls back to the default *.cloudfront.net certificate and aliases must be empty."
  type        = string
  default     = null
}

variable "aliases" {
  description = "Alternate domain names (CNAMEs) on the CloudFront distribution. Every entry must be covered by the certificate at acm_certificate_arn. Empty when no custom domain is configured."
  type        = list(string)
  default     = []
}
