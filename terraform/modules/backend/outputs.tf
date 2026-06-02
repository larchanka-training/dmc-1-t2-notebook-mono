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

output "api_target_group_arn" {
  description = "ALB target group ARN for the API."
  value       = aws_lb_target_group.api.arn
}
