# Preview-cloud shared layer (preview-v2). A dedicated, persistent layer shared
# by all per-PR previews: its own VPC, ECS cluster, ALB, RDS, CloudFront, S3 —
# fully isolated from prod (terraform/cloud). Per-PR slices (services, target
# groups, ALB rules, pr_<N> databases, /pr-<N>/ static) are created imperatively
# from CI, not here. See docs/preview-v2.md (decisions A/B/C).
#
# Built in phases:
#   P1a — network (this file): own VPC 10.1.0.0/16, subnets, NAT, SG chain.
#   P1b — shared backend: ECS cluster, ALB + default listener, IAM.
#   P1c — data: preview RDS + master credentials secret (CI creates pr_<N> DBs).
#   P1d — frontend: S3 + CloudFront with wildcard /pr-*/ routing.

module "network" {
  source = "../modules/network"

  project  = var.project
  vpc_cidr = var.vpc_cidr

  public_subnet_cidrs  = ["10.1.1.0/24", "10.1.2.0/24"]
  private_subnet_cidrs = ["10.1.11.0/24", "10.1.12.0/24"]
}

module "preview_shared" {
  source = "../modules/preview-shared"

  project               = var.project
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  private_subnet_ids    = module.network.private_subnet_ids
  rds_security_group_id = module.network.rds_security_group_id
}
