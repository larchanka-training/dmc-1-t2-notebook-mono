# Cloud-native production stack (ECS Fargate + RDS + S3/CloudFront).
# Built up in phases; see docs/preview-dev-environments-v2.md and
# larchanka-training/js-notebook#110.
#
# Phase 0 — network: VPC, subnets, NAT, route tables, SG chain.
# Phase 1 — backend: ECS Fargate + ALB + IAM + Secrets + CloudWatch logs.
# Phase 2 — frontend: S3 + CloudFront.
# Phase 3 — data: RDS PostgreSQL + DATABASE_URL secret value.

module "network" {
  source = "../modules/network"

  project = var.project
}

module "backend" {
  source = "../modules/backend"

  project    = var.project
  aws_region = var.aws_region
  image_tag  = var.image_tag

  # API runs once the database exists (Phase 3). ECS retries tasks until the
  # DATABASE_URL secret value and RDS are ready, then they go healthy.
  desired_count = var.api_desired_count

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
}

module "data" {
  source = "../modules/data"

  project                 = var.project
  private_subnet_ids      = module.network.private_subnet_ids
  rds_security_group_id   = module.network.rds_security_group_id
  database_url_secret_arn = module.backend.database_url_secret_arn
}
