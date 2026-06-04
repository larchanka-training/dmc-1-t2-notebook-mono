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

# Preview secrets: the shared ones (${project}-main-database-url, -db-master) and
# per-PR ones (${project}-pr-<N>-*), all created in this namespace. Allow reading
# the whole preview namespace via a wildcard.
data "aws_iam_policy_document" "secrets_read" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project}-*"]
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
# The generated value feeds both aws_db_instance.password and the DATABASE_URL
# secret, so a regeneration updates the RDS master password and the secret in the
# same apply — they cannot diverge into a lockout.
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

  # Initial database for the shared main-api. Per-PR databases (pr_<N>) are
  # created by CI via the master connection.
  db_name  = var.main_db_name
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

# --- Frontend: S3 + CloudFront (wildcard /pr-*/ routing) ------------------

# One shared bucket holds every PR's static UI under a /pr-<N>/ prefix; CI syncs
# the build to /pr-<N>/ and removes it on PR close.
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# SPA routing that preserves the /pr-<N>/ prefix: an extensionless request under
# /pr-<N>/ is rewritten to /pr-<N>/index.html so each PR's client-side routes
# resolve to its own app. Static assets (with an extension) pass through.
resource "aws_cloudfront_function" "spa" {
  name    = "${var.project}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);
      if (lastSegment.indexOf('.') !== -1) {
        return request;
      }
      var parts = uri.split('/');
      if (parts.length > 1 && parts[1].indexOf('pr-') === 0) {
        request.uri = '/' + parts[1] + '/index.html';
      } else {
        request.uri = '/index.html';
      }
      return request;
    }
  EOT
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "this" {
  enabled     = true
  comment     = "${var.project} frontend"
  price_class = var.price_class

  origin {
    origin_id                = "s3-frontend"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = "preview-alb"
    domain_name = aws_lb.this.dns_name

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB is HTTP until the TLS phase
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Default: everything -> S3 static (SPA rewrite keeps the /pr-<N>/ prefix).
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa.arn
    }
  }

  # /api/v1/* -> preview ALB -> shared main-api (the stable backend UI previews
  # talk to). No caching, forward everything except Host.
  ordered_cache_behavior {
    path_pattern             = "/api/v1/*"
    target_origin_id         = "preview-alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  # /pr-<N>/api/v1/* -> preview ALB -> per-PR backend (routing 3a: the PR backend
  # serves under API_PREFIX=/pr-<N>/api/v1, ALB routes by path to the PR's target
  # group). No caching, forward everything except Host.
  ordered_cache_behavior {
    path_pattern             = "/pr-*/api/v1/*"
    target_origin_id         = "preview-alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "frontend_s3" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_s3.json
}

# --- Shared main-api backend (stable API that UI previews talk to) --------

# DATABASE_URL for the shared main-api (the preview_main database).
resource "aws_secretsmanager_secret" "main_database_url" {
  name        = "${var.project}-main-database-url"
  description = "DATABASE_URL for the shared preview main-api (preview_main DB)."
}

resource "aws_secretsmanager_secret_version" "main_database_url" {
  secret_id     = aws_secretsmanager_secret.main_database_url.id
  secret_string = "postgresql://${var.db_username}:${random_password.db.result}@${aws_db_instance.this.endpoint}/${var.main_db_name}"
}

resource "aws_lb_target_group" "main_api" {
  name                 = "${var.project}-main-api-tg"
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

  tags = { Name = "${var.project}-main-api-tg" }
}

# /api/v1/* -> main-api. Per-PR rules (/pr-<N>/api/v1/*) are added by CI with
# their own priorities; paths don't overlap, so priority order is not critical.
resource "aws_lb_listener_rule" "main_api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main_api.arn
  }

  condition {
    path_pattern {
      values = ["/api/v1/*"]
    }
  }
}

# Shared main-api task definition. APP_ENV is left at its default ("dev") — stub
# auth + dev-seed context are fine for previews. The preview deploy registers a
# new revision with the current main image per release.
resource "aws_ecs_task_definition" "main_api" {
  family                   = "${var.project}-main-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name         = "api"
    image        = "${var.ecr_registry}/${var.ecr_repository}:api-${var.api_image_tag}"
    essential    = true
    portMappings = [{ containerPort = var.api_port, protocol = "tcp" }]

    secrets = [{
      name      = "DATABASE_URL"
      valueFrom = aws_secretsmanager_secret.main_database_url.arn
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "main-api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:${var.api_port}/api/v1/health', timeout=3)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }
  }])
}

resource "aws_ecs_service" "main_api" {
  name            = "${var.project}-main-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.main_api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.main_api.arn
    container_name   = "api"
    container_port   = var.api_port
  }

  # The preview deploy registers revisions; don't let Terraform revert them.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener_rule.main_api]
}

# --- Migration task definition (preview) ----------------------------------

# Run as a one-off `aws ecs run-task` by CI to migrate preview_main and per-PR
# pr_<N> databases. CI overrides LIQUIBASE_COMMAND_URL (target DB) and
# LIQUIBASE_COMMAND_CONTEXTS (= "dev" for previews, so the dev-seed applies) per
# run; username/password come from the master secret.
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
    image     = "${var.ecr_registry}/${var.ecr_repository}:migrations-${var.api_image_tag}"
    essential = true

    environment = [{
      name  = "LIQUIBASE_COMMAND_CHANGELOG_FILE"
      value = "changelog-master.xml"
    }]

    secrets = [
      { name = "LIQUIBASE_COMMAND_USERNAME", valueFrom = "${aws_secretsmanager_secret.db_master.arn}:username::" },
      { name = "LIQUIBASE_COMMAND_PASSWORD", valueFrom = "${aws_secretsmanager_secret.db_master.arn}:password::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "migrations"
      }
    }
  }])
}
