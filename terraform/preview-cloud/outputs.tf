output "vpc_id" {
  description = "Preview VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (preview ALB, NAT)."
  value       = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs (preview ECS tasks, RDS)."
  value       = module.network.private_subnet_ids
}

output "alb_security_group_id" {
  description = "Preview ALB security group."
  value       = module.network.alb_security_group_id
}

output "ecs_security_group_id" {
  description = "Preview ECS security group."
  value       = module.network.ecs_security_group_id
}

output "rds_security_group_id" {
  description = "Preview RDS security group."
  value       = module.network.rds_security_group_id
}

output "ecs_cluster_name" {
  description = "Preview ECS cluster name."
  value       = module.preview_shared.ecs_cluster_name
}

output "alb_dns_name" {
  description = "Preview ALB DNS name."
  value       = module.preview_shared.alb_dns_name
}

output "alb_listener_arn" {
  description = "Preview ALB :80 listener ARN (CI attaches per-PR rules here)."
  value       = module.preview_shared.alb_listener_arn
}

output "execution_role_arn" {
  description = "IAM execution role ARN for per-PR task definitions."
  value       = module.preview_shared.execution_role_arn
}

output "task_role_arn" {
  description = "IAM task role ARN for per-PR task definitions."
  value       = module.preview_shared.task_role_arn
}

output "log_group_name" {
  description = "CloudWatch log group for preview tasks."
  value       = module.preview_shared.log_group_name
}

output "db_endpoint" {
  description = "Preview RDS endpoint (host:port)."
  value       = module.preview_shared.db_endpoint
}

output "db_master_secret_arn" {
  description = "ARN of the preview RDS master credentials secret (read by CI)."
  value       = module.preview_shared.db_master_secret_arn
}

output "bastion_instance_id" {
  description = "SSM bastion instance ID (null when create_bastion = false). The --target of `aws ssm start-session`."
  value       = var.create_bastion ? module.bastion[0].instance_id : null
}

# Ready-to-paste tunnel: opens localhost:5433 → preview RDS:5432 through the
# bastion (needs the AWS CLI Session Manager plugin). Local port 5433 (not 5432)
# so a prod tunnel on 5432 can run at the same time. Connect pgAdmin to
# localhost:5433 with the master creds from the jsnotes-t2-preview-db-master secret.
output "db_tunnel_command" {
  description = "Command to open a local pgAdmin tunnel to the preview RDS via the bastion (null when create_bastion = false)."
  value = var.create_bastion ? join("", [
    "aws ssm start-session --region ${var.aws_region}",
    " --target ${module.bastion[0].instance_id}",
    " --document-name AWS-StartPortForwardingSessionToRemoteHost",
    " --parameters '{\"host\":[\"${element(split(":", module.preview_shared.db_endpoint), 0)}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}'"
  ]) : null
}

output "frontend_bucket" {
  description = "S3 bucket holding per-PR static UI under /pr-<N>/."
  value       = module.preview_shared.frontend_bucket
}

output "cloudfront_domain_name" {
  description = "Preview CloudFront domain (per-PR URL: https://<domain>/pr-<N>/)."
  value       = module.preview_shared.cloudfront_domain_name
}

output "cloudfront_distribution_id" {
  description = "Preview CloudFront distribution ID."
  value       = module.preview_shared.cloudfront_distribution_id
}

output "main_api_service_name" {
  description = "Shared main-api ECS service name."
  value       = module.preview_shared.main_api_service_name
}

output "main_api_task_family" {
  description = "Shared main-api task-definition family."
  value       = module.preview_shared.main_api_task_family
}

output "migration_task_family" {
  description = "Preview migration task-definition family."
  value       = module.preview_shared.migration_task_family
}

# Deploy baselines: deploy-preview.yml renders releases from these
# Terraform-registered revisions — see modules/preview-shared/outputs.tf.
output "main_api_task_definition_arn" {
  value = module.preview_shared.main_api_task_definition_arn
}

output "migration_task_definition_arn" {
  value = module.preview_shared.migration_task_definition_arn
}
