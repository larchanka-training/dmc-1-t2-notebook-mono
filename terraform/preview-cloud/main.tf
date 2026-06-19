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

  # No NAT for now — preview egress to AWS services goes through VPC endpoints
  # (see modules/preview-shared). We WANT a NAT here for parity with prod (so
  # preview tasks also get arbitrary-internet egress), but it is BLOCKED: the
  # regional Elastic IP quota is exhausted (17/17 allocated, 0 free; L-0263D0A3)
  # and a NAT requires an EIP, so create_nat=true would fail on
  # AllocateAddress → AddressLimitExceeded. Unresolved as of 2026-06-17 —
  # request an EIP quota increase, then flip to true. See docs/preview-v2.md (D).
  create_nat = false

  # Open RDS 5432 to the bastion SG when the bastion is enabled (DB access path).
  create_bastion = var.create_bastion
}

# SSM bastion for reaching the preview RDS from a developer laptop (pgAdmin).
# Public subnet + public IP because this VPC has no NAT — the SSM agent reaches
# the service via the IGW (cheaper than 3 SSM interface endpoints). No inbound
# rules, no SSH key, IAM-gated and audited.
module "bastion" {
  count  = var.create_bastion ? 1 : 0
  source = "../modules/bastion"

  project           = var.project
  subnet_id         = module.network.public_subnet_ids[0]
  security_group_id = module.network.bastion_security_group_id
  assign_public_ip  = true
}

module "preview_shared" {
  source = "../modules/preview-shared"

  project                = var.project
  aws_region             = var.aws_region
  vpc_id                 = module.network.vpc_id
  public_subnet_ids      = module.network.public_subnet_ids
  alb_security_group_id  = module.network.alb_security_group_id
  private_subnet_ids     = module.network.private_subnet_ids
  rds_security_group_id  = module.network.rds_security_group_id
  ecs_security_group_id  = module.network.ecs_security_group_id
  private_route_table_id = module.network.private_route_table_id
}
