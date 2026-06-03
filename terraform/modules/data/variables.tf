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
