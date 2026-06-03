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
