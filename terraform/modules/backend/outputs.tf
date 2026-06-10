output "alb_dns_name" {
  description = "Public DNS name of the ALB (API entry point)."
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  description = "ALB ARN."
  value       = aws_lb.this.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.api.name
}

output "database_url_secret_arn" {
  description = "ARN of the DATABASE_URL secret (value set in the data phase)."
  value       = aws_secretsmanager_secret.database_url.arn
}

output "migration_secret_arn" {
  description = "ARN of the Liquibase migration connection secret (value set in the data phase)."
  value       = aws_secretsmanager_secret.db_migration.arn
}

output "migration_task_def_family" {
  description = "ECS task-definition family for the one-off Liquibase migration task."
  value       = aws_ecs_task_definition.migration.family
}

# Canonical task-definition baselines. Terraform is the single owner of the task
# definition's shape (env, secrets, roles); the deploy pipeline renders each
# release FROM these revisions (swapping only the image), never from the live
# service's latest family revision — so env/secrets cannot drift between IaC
# and what actually runs.
output "api_task_definition_arn" {
  description = "Terraform-registered API task-def revision (deploy baseline)."
  value       = aws_ecs_task_definition.api.arn
}

output "migration_task_definition_arn" {
  description = "Terraform-registered migration task-def revision (deploy baseline)."
  value       = aws_ecs_task_definition.migration.arn
}

output "api_target_group_arn" {
  description = "ALB target group ARN for the API."
  value       = aws_lb_target_group.api.arn
}
