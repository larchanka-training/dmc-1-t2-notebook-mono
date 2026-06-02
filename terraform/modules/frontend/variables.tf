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
