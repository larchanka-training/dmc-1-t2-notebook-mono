# VPC endpoints — egress for private-subnet tasks WITHOUT a NAT gateway / Elastic
# IP. The preview VPC is created with create_nat=false (the regional EIP limit is
# exhausted), so preview tasks reach the AWS services they need through endpoints
# instead of the internet:
#   - ECR (api + dkr) — pull the api/migrations images
#   - S3 (gateway)    — ECR image layers are stored in S3
#   - Secrets Manager — read DB credentials
#   - CloudWatch Logs — write task logs
# RDS is in-VPC, so it needs no endpoint. Tasks have NO arbitrary-internet egress
# here (by design); external calls would go through a backend proxy or a NAT.

# Security group for the interface endpoints: HTTPS from the ECS tasks.
resource "aws_security_group" "endpoints" {
  name        = "${var.project}-vpce-sg"
  description = "VPC interface endpoints: HTTPS (443) from the ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTPS from ECS tasks"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
  }

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-vpce-sg" }
}

# S3 — gateway endpoint (free). Adds a route in the private route table; ECR
# pulls fetch layers from S3 through it.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [var.private_route_table_id]

  tags = { Name = "${var.project}-vpce-s3" }
}

# Interface endpoints — an ENI per private subnet with private DNS, so the normal
# AWS service hostnames resolve to the endpoint instead of the public internet.
locals {
  interface_endpoints = [
    "ecr.api",
    "ecr.dkr",
    "secretsmanager",
    "logs",
  ]
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoints)

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.project}-vpce-${replace(each.key, ".", "-")}" }
}
