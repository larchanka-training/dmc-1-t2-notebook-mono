output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "alb_security_group_id" {
  value = module.network.alb_security_group_id
}

output "ecs_security_group_id" {
  value = module.network.ecs_security_group_id
}

output "rds_security_group_id" {
  value = module.network.rds_security_group_id
}

output "alb_dns_name" {
  description = "Public DNS of the ALB (API entry point)."
  value       = module.backend.alb_dns_name
}

output "ecs_cluster_name" {
  value = module.backend.ecs_cluster_name
}

output "database_url_secret_arn" {
  value = module.backend.database_url_secret_arn
}

# Deploy baselines: the pipeline (deploy-cloud.yml) renders each release from
# these Terraform-registered revisions — see modules/backend/outputs.tf.
output "api_task_definition_arn" {
  value = module.backend.api_task_definition_arn
}

output "migration_task_definition_arn" {
  value = module.backend.migration_task_definition_arn
}

output "cloudfront_domain_name" {
  description = "Public app URL (until a custom domain is added)."
  value       = module.frontend.cloudfront_domain_name
}

output "frontend_bucket" {
  value = module.frontend.frontend_bucket
}

output "db_endpoint" {
  description = "RDS endpoint (host:port)."
  value       = module.data.db_endpoint
}

output "alerts_topic_arn" {
  description = "SNS topic CloudWatch alarms publish to."
  value       = module.observability.alerts_topic_arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard for prod health."
  value       = module.observability.dashboard_name
}
