variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "alerts_email" {
  description = "Email address subscribed to the alerts SNS topic. Empty string → the topic is still created but no email subscription is made (subscribe later). Set via the TF_VAR_alerts_email GitHub Actions variable."
  type        = string
  default     = ""
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix (CloudWatch LoadBalancer dimension)."
  type        = string
}

variable "api_target_group_arn_suffix" {
  description = "API target group ARN suffix (CloudWatch TargetGroup dimension)."
  type        = string
}

variable "ecs_cluster_name" {
  description = "ECS cluster name (CloudWatch ClusterName dimension)."
  type        = string
}

variable "ecs_service_name" {
  description = "ECS service name (CloudWatch ServiceName dimension)."
  type        = string
}

variable "db_instance_identifier" {
  description = "RDS instance identifier (CloudWatch DBInstanceIdentifier dimension) — the human name (jsnotes-t2-db), NOT the db-XXXX resource id."
  type        = string
}

variable "rds_free_storage_threshold_bytes" {
  description = "Alarm when RDS FreeStorageSpace drops below this (bytes). Default 2 GiB."
  type        = number
  default     = 2147483648
}

variable "rds_max_connections" {
  description = "Alarm when RDS DatabaseConnections exceeds this. Conservative default for db.t3.micro."
  type        = number
  default     = 80
}
