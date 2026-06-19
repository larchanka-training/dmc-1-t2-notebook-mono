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

variable "create_bastion" {
  description = "Create the SSM bastion for reaching the preview RDS from a developer laptop (pgAdmin). Sits in a public subnet with a public IP because the preview VPC has no NAT — the SSM agent reaches the service via the IGW. Still no inbound, no SSH key. Default on; stop the instance, or set false and apply, to drop the ~$3-4/mo cost when idle."
  type        = bool
  default     = true
}
