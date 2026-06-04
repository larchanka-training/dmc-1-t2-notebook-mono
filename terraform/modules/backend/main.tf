# Backend: ECS Fargate service for the API, fronted by an ALB, with IAM roles,
# a Secrets Manager secret for DATABASE_URL, and CloudWatch logs.
#
# Notes:
#   - desired_count defaults to 0: the service won't run tasks until RDS exists
#     and the DATABASE_URL secret has a value (Phase 3). All resources are still
#     created so the wiring is reviewable.
#   - The image tag should be an immutable sha-<short> in real deploys; the
#     deploy pipeline registers a new task-definition revision per release.
#   - DB migrations (Liquibase): this module defines the migration task
#     definition + its secret, but migrations are RUN at deploy time as a one-off
#     `aws ecs run-task` (deploy-cloud.yml), not by Terraform.

locals {
  api_image       = "${var.ecr_registry}/${var.ecr_repository}:api-${var.image_tag}"
  migration_image = "${var.ecr_registry}/${var.ecr_repository}:migrations-${var.image_tag}"
}

# --- CloudWatch logs ------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "migration" {
  name              = "/ecs/${var.project}-migrations"
  retention_in_days = var.log_retention_days
}

# --- Secrets --------------------------------------------------------------

# The secret container is created here; its value (the real DATABASE_URL) is
# populated in the data phase once the RDS endpoint is known.
resource "aws_secretsmanager_secret" "database_url" {
  name        = "${var.project}-database-url"
  description = "PostgreSQL DATABASE_URL for the API (value set with RDS in Phase 3)."
}

# Liquibase connection for the migration task (JSON: url/username/password).
# Container created here; its value (JDBC url + creds) is set in the data phase.
resource "aws_secretsmanager_secret" "db_migration" {
  name        = "${var.project}-db-migration"
  description = "Liquibase connection (url/username/password JSON) for the migration task; value set in Phase 3."
}

# --- IAM roles ------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: used by the ECS agent to pull the image, read secrets, and
# write logs (before the container starts).
resource "aws_iam_role" "execution" {
  name               = "${var.project}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "secrets_read" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.database_url.arn,
      aws_secretsmanager_secret.db_migration.arn,
    ]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.project}-ecs-secrets-read"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

# Task role: identity of the running container (for the app's own AWS calls).
# Empty for now — a home for SES/etc. permissions later.
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# --- Application Load Balancer --------------------------------------------

resource "aws_lb" "this" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = { Name = "${var.project}-alb" }
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.project}-api-tg"
  port                 = var.api_port
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  target_type          = "ip"
  deregistration_delay = 30

  health_check {
    path                = "/api/v1/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  tags = { Name = "${var.project}-api-tg" }
}

# HTTP listener — forwards everything to the API. HTTPS (:443) is added in the
# TLS phase; for now CloudFront / direct ALB DNS is HTTP.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# --- ECS ------------------------------------------------------------------

resource "aws_ecs_cluster" "this" {
  name = var.project
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = local.api_image
    essential = true

    portMappings = [{
      containerPort = var.api_port
      protocol      = "tcp"
    }]

    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = aws_secretsmanager_secret.database_url.arn
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }

    # Mirrors the api Dockerfile healthcheck (python urllib, no curl in image).
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${var.api_port}/api/v1/health', timeout=3)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }
  }])
}

# Migration task definition — run as a one-off `aws ecs run-task` by the deploy
# pipeline (deploy-cloud.yml) BEFORE the API service rolls out. No service: it
# runs to completion and exits. Network config (subnets/SG) is supplied at
# run-task time. Liquibase reads its connection from LIQUIBASE_COMMAND_* env,
# injected from the db_migration secret's JSON keys by the execution role.
resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.project}-migrations"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "migrations"
    image     = local.migration_image
    essential = true

    # CMD ["update"] is inherited from the migrations image.
    # LIQUIBASE_COMMAND_CONTEXTS is passed at deploy time via run-task overrides
    # (deploy-cloud.yml = production, so context="dev" changesets are skipped) —
    # keeping it out of the task def avoids a replace that the destructive guard
    # blocks on the branch.
    environment = [{
      name  = "LIQUIBASE_COMMAND_CHANGELOG_FILE"
      value = "changelog-master.xml"
    }]

    secrets = [
      { name = "LIQUIBASE_COMMAND_URL", valueFrom = "${aws_secretsmanager_secret.db_migration.arn}:url::" },
      { name = "LIQUIBASE_COMMAND_USERNAME", valueFrom = "${aws_secretsmanager_secret.db_migration.arn}:username::" },
      { name = "LIQUIBASE_COMMAND_PASSWORD", valueFrom = "${aws_secretsmanager_secret.db_migration.arn}:password::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.migration.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${var.project}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # Zero-downtime rolling deploys.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Auto-rollback a failed deploy (T1 lacks this).
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Debug a task without SSH/bastion: aws ecs execute-command.
  enable_execute_command = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.api_port
  }

  # Terraform creates the baseline task definition; the deploy pipeline
  # (deploy-cloud.yml) registers new revisions per release. Ignore task_definition
  # here so `terraform apply` doesn't revert what the pipeline deployed.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
