variable "project" {
  description = "Resource name prefix for the preview shared layer (e.g. jsnotes-t2-preview)."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the preview ALB."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group for the preview ALB."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention for preview tasks (short — these are throwaway)."
  type        = number
  default     = 7
}
