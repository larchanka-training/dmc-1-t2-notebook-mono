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

# --- Data: preview RDS (master) -------------------------------------------

# Shared preview Postgres. CI creates one database per PR (pr_<N>) via the
# master connection; there is no per-app initial database here. Unlike prod
# this instance is disposable: no deletion protection, no final snapshot.

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.project}-db-subnet-group" }
}

# special = false keeps the password URL-safe in DATABASE_URLs.
resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_db_instance" "this" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  # No db_name: CI creates pr_<N> databases; the master connects to the default
  # "postgres" database.
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.rds_security_group_id]

  multi_az                = false
  backup_retention_period = 1

  # Disposable preview instance — must be easy to tear down.
  deletion_protection = false
  skip_final_snapshot = true

  tags = { Name = "${var.project}-db" }
}

# Master credentials for CI: create/drop pr_<N> databases and build per-PR
# DATABASE_URLs. JSON keys: username/password/host/port.
resource "aws_secretsmanager_secret" "db_master" {
  name        = "${var.project}-db-master"
  description = "Preview RDS master credentials (CI creates/drops pr_<N> databases)."
}

resource "aws_secretsmanager_secret_version" "db_master" {
  secret_id = aws_secretsmanager_secret.db_master.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
  })
}
