# Cloud-native production stack (ECS Fargate + RDS + S3/CloudFront).
# Built up in phases; see docs/preview-dev-environments-v2.md and
# larchanka-training/js-notebook#110.
#
# Phase 0 — network (this commit): VPC, subnets, NAT, route tables, SG chain.
# Phase 1 — ECS Fargate + ALB + IAM + Secrets + CloudWatch logs (next).
# Phase 2 — S3 + CloudFront (frontend).
# Phase 3 — RDS + data migration.

module "network" {
  source = "../modules/network"

  project = var.project
}
