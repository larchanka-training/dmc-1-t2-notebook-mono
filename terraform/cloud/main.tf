# Cloud-native production stack (ECS Fargate + RDS + S3/CloudFront).
# Built up in phases; see docs/preview-dev-environments-v2.md and
# larchanka-training/js-notebook#110.
#
# Phase 0 — network: VPC, subnets, NAT, route tables, SG chain.
# Phase 1 — backend: ECS Fargate + ALB + IAM + Secrets + CloudWatch logs.
# Phase 2 — S3 + CloudFront (frontend) — next.
# Phase 3 — RDS + data migration — next.

module "network" {
  source = "../modules/network"

  project = var.project
}

module "backend" {
  source = "../modules/backend"

  project    = var.project
  aws_region = var.aws_region
  image_tag  = var.image_tag

  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  ecs_security_group_id = module.network.ecs_security_group_id
}
