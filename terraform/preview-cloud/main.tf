# Preview-cloud shared layer (preview-v2). A dedicated, persistent layer shared
# by all per-PR previews: its own VPC, ECS cluster, ALB, RDS, CloudFront, S3 —
# fully isolated from prod (terraform/cloud). Per-PR slices (services, target
# groups, ALB rules, /pr-<N>/ static) are created imperatively from CI, not here.
# Per-PR API services share the one preview_main database (option B — no per-PR
# DB yet). See docs/preview-v2.md (decisions A–D).
#
# Built in phases:
#   P1a — network (this file): own VPC 10.1.0.0/16, subnets, NAT, SG chain.
#   P1b — shared backend: ECS cluster, ALB + default listener, IAM.
#   P1c — data: preview RDS + master credentials secret (shared preview_main DB).
#   P1d — frontend: S3 + CloudFront with wildcard /pr-*/ routing.

module "network" {
  source = "../modules/network"

  project  = var.project
  vpc_cidr = var.vpc_cidr

  public_subnet_cidrs  = ["10.1.1.0/24", "10.1.2.0/24"]
  private_subnet_cidrs = ["10.1.11.0/24", "10.1.12.0/24"]

  # No NAT/Elastic IP (regional EIP limit is exhausted). Private-subnet egress
  # to AWS services goes through VPC endpoints (see modules/preview-shared).
  create_nat = false
}

module "preview_shared" {
  source = "../modules/preview-shared"

  project                = var.project
  aws_region             = var.aws_region
  app_environment        = var.app_environment
  vpc_id                 = module.network.vpc_id
  public_subnet_ids      = module.network.public_subnet_ids
  alb_security_group_id  = module.network.alb_security_group_id
  private_subnet_ids     = module.network.private_subnet_ids
  rds_security_group_id  = module.network.rds_security_group_id
  ecs_security_group_id  = module.network.ecs_security_group_id
  private_route_table_id = module.network.private_route_table_id
}
