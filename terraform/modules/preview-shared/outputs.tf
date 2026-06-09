output "ecs_cluster_name" {
  description = "Preview ECS cluster name (per-PR services are created here)."
  value       = aws_ecs_cluster.this.name
}

output "ecs_cluster_arn" {
  description = "Preview ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "alb_arn" {
  description = "Preview ALB ARN."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "Preview ALB DNS name (CloudFront origin for /pr-*/api/v1/*)."
  value       = aws_lb.this.dns_name
}

output "alb_listener_arn" {
  description = "Preview ALB :80 listener ARN (CI attaches per-PR rules here)."
  value       = aws_lb_listener.http.arn
}

output "execution_role_arn" {
  description = "IAM execution role ARN for per-PR task definitions."
  value       = aws_iam_role.execution.arn
}

output "task_role_arn" {
  description = "IAM task role ARN for per-PR task definitions."
  value       = aws_iam_role.task.arn
}

output "log_group_name" {
  description = "CloudWatch log group for preview tasks."
  value       = aws_cloudwatch_log_group.this.name
}

output "db_endpoint" {
  description = "Preview RDS endpoint (host:port)."
  value       = aws_db_instance.this.endpoint
}

output "db_address" {
  description = "Preview RDS host."
  value       = aws_db_instance.this.address
}

output "db_master_secret_arn" {
  description = "ARN of the preview RDS master credentials secret (read by CI)."
  value       = aws_secretsmanager_secret.db_master.arn
}

output "frontend_bucket" {
  description = "S3 bucket holding per-PR static UI under /pr-<N>/."
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_domain_name" {
  description = "Preview CloudFront domain (per-PR URL: https://<domain>/pr-<N>/)."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "cloudfront_distribution_id" {
  description = "Preview CloudFront distribution ID (CI invalidations)."
  value       = aws_cloudfront_distribution.this.id
}

output "main_api_service_name" {
  description = "Shared main-api ECS service name."
  value       = aws_ecs_service.main_api.name
}

output "main_api_task_family" {
  description = "Shared main-api task-definition family."
  value       = aws_ecs_task_definition.main_api.family
}

output "main_database_url_secret_arn" {
  description = "ARN of the shared main-api DATABASE_URL secret."
  value       = aws_secretsmanager_secret.main_database_url.arn
}

output "migration_task_family" {
  description = "Preview migration task-definition family (CI run-task; override URL + contexts)."
  value       = aws_ecs_task_definition.migration.family
}

# Canonical task-definition baselines (prod parity — see modules/backend).
# deploy-preview.yml renders releases from these Terraform-registered revisions,
# never from the live family's latest revision, so env/secrets can't drift.
output "main_api_task_definition_arn" {
  description = "Terraform-registered main-api task-def revision (deploy baseline)."
  value       = aws_ecs_task_definition.main_api.arn
}

output "migration_task_definition_arn" {
  description = "Terraform-registered preview migration task-def revision (deploy baseline)."
  value       = aws_ecs_task_definition.migration.arn
}
