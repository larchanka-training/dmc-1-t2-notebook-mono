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

output "bastion_instance_id" {
  description = "SSM bastion instance ID (null when create_bastion = false). The --target of `aws ssm start-session`."
  value       = var.create_bastion ? module.bastion[0].instance_id : null
}

# Ready-to-paste tunnel: opens localhost:5432 → RDS:5432 through the bastion
# (needs the AWS CLI Session Manager plugin). Then connect pgAdmin to
# localhost:5432 with the master creds from the jsnotes-t2-database-url secret.
output "db_tunnel_command" {
  description = "Command to open a local pgAdmin tunnel to RDS via the bastion (null when create_bastion = false)."
  value = var.create_bastion ? join("", [
    "aws ssm start-session --region ${var.aws_region}",
    " --target ${module.bastion[0].instance_id}",
    " --document-name AWS-StartPortForwardingSessionToRemoteHost",
    " --parameters '{\"host\":[\"${element(split(":", module.data.db_endpoint), 0)}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}'"
  ]) : null
}

output "route53_health_check_id" {
  description = "Route 53 health check ID monitoring the public URL from outside AWS (AWS Console → Route 53 → Health checks)."
  value       = aws_route53_health_check.public_api.id
}
