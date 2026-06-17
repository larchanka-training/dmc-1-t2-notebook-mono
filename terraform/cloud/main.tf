# Cloud-native production stack (ECS Fargate + RDS + S3/CloudFront).
# Architecture, phases and current status: docs/aws-cloud-migration.md
# Umbrella task: larchanka-training/js-notebook#110.
# (docs/preview-dev-environments-v2.md is the historical decision record only.)
#
# Phase 0 — network: VPC, subnets, NAT, route tables, SG chain.
# Phase 1 — backend: ECS Fargate + ALB + IAM + Secrets + CloudWatch logs.
# Phase 2 — frontend: S3 + CloudFront.
# Phase 3 — data: RDS PostgreSQL + DATABASE_URL secret value.
#
# Production-readiness (HA):
#   - backend: Application Auto Scaling (min 2 / max 6, CPU-tracked) → always ≥2
#     API tasks spread across AZs, scaling out under load.
#   - data: Multi-AZ RDS standby + Performance Insights + Enhanced Monitoring +
#     storage autoscaling, 14-day backups.
# Observability — CloudWatch alarms / SNS / dashboard — see monitoring.tf.

module "network" {
  source = "../modules/network"

  project = var.project
}

module "backend" {
  source = "../modules/backend"

  project         = var.project
  aws_region      = var.aws_region
  image_tag       = var.image_tag
  app_environment = var.app_environment

  # API runs once the database exists (Phase 3). ECS retries tasks until the
  # DATABASE_URL secret value and RDS are ready, then they go healthy.
  desired_count = var.api_desired_count

  alert_emails = var.alert_emails

  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  ecs_security_group_id = module.network.ecs_security_group_id
}

module "frontend" {
  source = "../modules/frontend"

  project      = var.project
  alb_dns_name = module.backend.alb_dns_name
  # Empty-string from CI (unset GitHub variable) → null, so the module falls
  # back to the default CloudFront cert and aliases stay disabled.
  acm_certificate_arn = var.frontend_acm_certificate_arn != "" ? var.frontend_acm_certificate_arn : null
  aliases             = var.frontend_aliases
}

module "data" {
  source = "../modules/data"

  project                 = var.project
  private_subnet_ids      = module.network.private_subnet_ids
  rds_security_group_id   = module.network.rds_security_group_id
  database_url_secret_arn = module.backend.database_url_secret_arn
  migration_secret_arn    = module.backend.migration_secret_arn

  # Production-grade RDS: a synchronous standby in a second AZ (auto-failover),
  # longer backups, query-level + OS-level monitoring, and storage autoscaling
  # so a filling disk grows instead of taking the DB down.
  multi_az                     = true
  backup_retention_days        = 14
  performance_insights_enabled = true
  max_allocated_storage        = 100
  monitoring_interval          = 60
  # Online/no-reboot changes → apply on merge, not at the next maintenance window.
  apply_immediately = true
}
