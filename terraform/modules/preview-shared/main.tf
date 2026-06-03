# Preview shared layer — the persistent bones shared by every per-PR preview:
# ECS cluster, ALB (+ a catch-all listener), IAM roles, CloudWatch logs. The
# per-PR slices (task defs, services, target groups, ALB rules) are created
# imperatively from CI; this module only provides what they attach to.
#
# Built in phases (see docs/preview-v2.md):
#   P1b (this file): cluster + ALB + default listener + IAM + log group.
#   P1c: preview RDS + master credentials secret.
#   P1d: S3 + CloudFront with wildcard /pr-*/ routing.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# --- ECS cluster ----------------------------------------------------------

resource "aws_ecs_cluster" "this" {
  name = var.project
}

# --- CloudWatch logs ------------------------------------------------------

# One log group for all preview tasks; per-PR tasks use stream prefixes.
resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project}"
  retention_in_days = var.log_retention_days
}

# --- ALB ------------------------------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = { Name = "${var.project}-alb" }
}

# Default listener: no fixed backend. CI adds per-PR rules (path
# /pr-<N>/api/v1/* -> the PR's target group); anything unmatched gets a 404.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "No preview matched this path."
      status_code  = "404"
    }
  }
}

# --- IAM roles (shared by all per-PR task definitions) --------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pull images, read per-PR secrets, write logs (pre-start).
resource "aws_iam_role" "execution" {
  name               = "${var.project}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Per-PR secrets are named ${project}-pr-<N>-* and created by CI; allow reading
# the whole preview namespace via a wildcard.
data "aws_iam_policy_document" "secrets_read" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project}-pr-*"]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.project}-ecs-secrets-read"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Task role: identity of the running per-PR container (empty for now).
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}
