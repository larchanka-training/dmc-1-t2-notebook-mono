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

variable "private_subnet_ids" {
  description = "Private subnet IDs for the preview RDS subnet group."
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group for the preview RDS (5432 from the ECS SG only)."
  type        = string
}

variable "db_engine_version" {
  description = "PostgreSQL major version (match prod)."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  description = "Preview RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Preview RDS storage (GiB)."
  type        = number
  default     = 20
}

variable "db_username" {
  description = "Master DB username. Avoid engine-reserved names (PostgreSQL rejects 'admin')."
  type        = string
  default     = "jsnotes"
}
