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
