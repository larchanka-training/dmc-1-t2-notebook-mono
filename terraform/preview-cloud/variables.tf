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
