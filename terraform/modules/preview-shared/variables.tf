variable "project" {
  description = "Resource name prefix for the preview shared layer (e.g. jsnotes-t2-preview)."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID (for ALB target groups)."
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

variable "price_class" {
  description = "CloudFront price class (PriceClass_100 = cheapest, NA+EU)."
  type        = string
  default     = "PriceClass_100"
}

variable "aws_region" {
  description = "AWS region (awslogs driver + secret ARNs)."
  type        = string
  default     = "eu-north-1"
}

variable "ecs_security_group_id" {
  description = "Security group for the shared main-api ECS service (reuses private_subnet_ids)."
  type        = string
}

variable "private_route_table_id" {
  description = "Private route table ID (for the S3 gateway VPC endpoint)."
  type        = string
}

variable "ecr_registry" {
  description = "ECR registry host."
  type        = string
  default     = "867633231218.dkr.ecr.eu-north-1.amazonaws.com"
}

variable "ecr_repository" {
  description = "ECR repository (images tagged api-<tag> / migrations-<tag>)."
  type        = string
  default     = "jsnotes-t2"
}

variable "api_image_tag" {
  description = "Image tag for the shared main-api (runs main). The preview deploy overrides per release."
  type        = string
  default     = "latest"
}

variable "api_port" {
  description = "Container port the API listens on."
  type        = number
  default     = 8000
}

variable "api_cpu" {
  description = "Fargate CPU for the shared main-api."
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the shared main-api."
  type        = number
  default     = 512
}

variable "main_db_name" {
  description = "Database name for the shared main-api (per-PR DBs are pr_<N>, created by CI)."
  type        = string
  default     = "preview_main"
}

variable "app_environment" {
  description = "Non-secret env vars (one key = one env var) merged into the shared main-api task-def on top of the Bedrock config. APP_ENV is deliberately NOT set here — preview keeps the api default (\"dev\"). ENABLE_EXECUTE stays false by default; preview (APP_ENV=dev) is the only env where it may be flipped to true, since the prod hard-guard forbids it. Secrets go through Secrets Manager, not here."
  type        = map(string)
  default = {
    ENABLE_EXECUTE               = "false"
    LLM_CONTEXT_SUMMARY_STRATEGY = "compact-oldest"
    LLM_MAX_PROMPT_BYTES         = "8192"
  }
}

variable "bedrock_generator_model_id" {
  description = "Bedrock model ID for code generation (EU Geo inference profile). Mirrors the prod default; scoped in the preview task IAM policy and injected as LLM_BEDROCK_GENERATOR_MODEL_ID."
  type        = string
  default     = "eu.amazon.nova-lite-v1:0"
}

variable "bedrock_guard_model_id" {
  description = "Bedrock model ID for the prompt-injection pre-filter (EU Geo inference profile). Mirrors the prod default."
  type        = string
  default     = "eu.amazon.nova-micro-v1:0"
}

variable "bedrock_geo_regions" {
  description = "Destination regions the EU Nova Geo inference profile can route to from eu-north-1; the IAM policy grants invoke on the foundation-model ARN in each. Keep in sync with the identical default in modules/backend/variables.tf."
  type        = list(string)
  default     = ["eu-central-1", "eu-north-1", "eu-west-1", "eu-west-3"]
}
