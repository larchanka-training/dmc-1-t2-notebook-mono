variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group."
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group for RDS (allows 5432 from the ECS SG only)."
  type        = string
}

variable "database_url_secret_arn" {
  description = "ARN of the DATABASE_URL secret (created in the backend module); its value is set here once the RDS endpoint is known."
  type        = string
}

variable "migration_secret_arn" {
  description = "ARN of the Liquibase migration connection secret (created in the backend module); its JSON value (url/username/password) is set here once the RDS endpoint is known."
  type        = string
}

variable "db_name" {
  description = "Database name (matches the app / data migration)."
  type        = string
  default     = "wiki"
}

variable "db_username" {
  description = "Master DB username. Avoid engine-reserved names (PostgreSQL rejects 'admin', 'rdsadmin', etc.)."
  type        = string
  default     = "jsnotes"
}

variable "engine_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  description = "Allocated storage (GiB)."
  type        = number
  default     = 20
}

variable "backup_retention_days" {
  description = "Automated backup retention (days)."
  type        = number
  default     = 7
}

variable "multi_az" {
  description = "Run the DB as Multi-AZ — a synchronous standby in a second AZ with automatic failover (~60-120s). Doubles the instance cost; the prod stack enables it for zone-failure survival."
  type        = bool
  default     = false
}

variable "performance_insights_enabled" {
  description = "Enable RDS Performance Insights (query-level load visibility). Free for the 7-day retention tier; supported on db.t3.micro."
  type        = bool
  default     = false
}

variable "max_allocated_storage" {
  description = "Upper bound (GiB) for storage autoscaling — RDS grows allocated_storage toward this as the disk fills. null disables autoscaling (fixed size)."
  type        = number
  default     = null
}

variable "monitoring_interval" {
  description = "Enhanced Monitoring granularity in seconds (1/5/10/15/30/60). 0 disables it. When > 0 a monitoring IAM role is created automatically."
  type        = number
  default     = 0
}

variable "apply_immediately" {
  description = "Apply RDS modifications immediately instead of waiting for the next maintenance window. Every change this module makes (Multi-AZ, Performance Insights, Enhanced Monitoring, backup retention, storage autoscaling) is online / no-reboot, so true is safe and makes them take effect on apply rather than days later."
  type        = bool
  default     = false
}
