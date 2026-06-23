# CloudWatch Dashboard — key production metrics on one screen.
# Navigate to: AWS Console → CloudWatch → Dashboards → jsnotes-t2
#
# Rows:
#   Row 1 (y=1):  Request Count | 5xx Errors | Unhealthy Host Count
#   Row 2 (y=7):  Response Time (p50/p95/p99) | ECS CPU + Memory (Container Insights)
#   Row 3 (y=13): External Uptime (Route 53, see below)

locals {
  alb_suffix  = module.backend.alb_arn_suffix
  tg_suffix   = module.backend.api_tg_arn_suffix
  ecs_cluster = module.backend.ecs_cluster_name
  ecs_service = module.backend.ecs_service_name
  region      = var.aws_region
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 1
        properties = {
          markdown = "## ${var.project} — Production"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "Requests / min"
          view   = "timeSeries"
          region = local.region
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_suffix,
              { stat = "Sum", period = 60, label = "Requests" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "5xx Errors"
          view   = "timeSeries"
          region = local.region
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", local.alb_suffix,
              { stat = "Sum", period = 60, color = "#d62728", label = "ALB 5xx" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", local.alb_suffix,
              "TargetGroup", local.tg_suffix,
              { stat = "Sum", period = 60, color = "#ff7f0e", label = "Target 5xx" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 1
        width  = 8
        height = 6
        properties = {
          title  = "Healthy / Unhealthy Hosts"
          view   = "timeSeries"
          region = local.region
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", local.alb_suffix,
              "TargetGroup", local.tg_suffix,
              { stat = "Minimum", period = 60, color = "#2ca02c", label = "Healthy" }],
            ["AWS/ApplicationELB", "UnHealthyHostCount", "LoadBalancer", local.alb_suffix,
              "TargetGroup", local.tg_suffix,
              { stat = "Maximum", period = 60, color = "#d62728", label = "Unhealthy" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "API Response Time (seconds)"
          view   = "timeSeries"
          region = local.region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_suffix,
              { stat = "p50", period = 60, label = "p50" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_suffix,
              { stat = "p95", period = 60, color = "#ff7f0e", label = "p95" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_suffix,
              { stat = "p99", period = 60, color = "#d62728", label = "p99" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 7
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU / Memory (Container Insights)"
          view   = "timeSeries"
          region = local.region
          metrics = [
            ["ECS/ContainerInsights", "CpuUtilized", "ClusterName", local.ecs_cluster,
              "ServiceName", local.ecs_service,
              { stat = "Average", period = 60, label = "CPU (vCPU×100)" }],
            ["ECS/ContainerInsights", "MemoryUtilized", "ClusterName", local.ecs_cluster,
              "ServiceName", local.ecs_service,
              { stat = "Average", period = 60, color = "#9467bd", label = "Memory (MiB)" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 13
        width  = 8
        height = 6
        properties = {
          title  = "External Uptime (Route 53 → public URL)"
          view   = "timeSeries"
          # Route 53 health-check metrics are published only in us-east-1,
          # regardless of the dashboard's own region — CloudWatch dashboard
          # widgets can pull metrics from another region explicitly.
          region = "us-east-1"
          metrics = [
            ["AWS/Route53", "HealthCheckStatus", "HealthCheckId", aws_route53_health_check.public_api.id,
              { stat = "Minimum", period = 60, color = "#2ca02c", label = "1=healthy" }]
          ]
        }
      }
    ]
  })
}

# --- External synthetic check: Route 53 health check on the public URL ---
#
# Everything above watches AWS-internal signals (ALB/ECS) — it can't see
# failures in the part AWS doesn't let you probe from the inside: a broken
# CloudFront cache behavior, a DNS problem, or a deploy that points the
# public URL at something dead. A Route 53 health check polls the public
# CloudFront URL from outside AWS, the same way a real user's browser would.
#
# Path is /api/v1/health/ready (readiness, pings the DB) rather than the
# liveness path the ALB target group uses (modules/backend/main.tf) — this
# way the external check also catches a DB outage, which liveness
# intentionally ignores (ECS must not kill a healthy container just because
# the DB is briefly down).
#
# Route 53 health-check CloudWatch metrics live only in us-east-1 (Route 53
# is a global service with a single metrics home region), and a CloudWatch
# alarm's SNS action must be in the same region as the alarm — hence the
# separate us-east-1 SNS topic/subscriptions below instead of reusing
# module.backend's eu-north-1 topic. Same ALERT_EMAILS list, so confirming
# every address in both topics activates full coverage.

resource "aws_route53_health_check" "public_api" {
  fqdn              = module.frontend.cloudfront_domain_name
  port              = 443
  type              = "HTTPS"
  resource_path     = "/api/v1/health/ready"
  request_interval  = 30
  failure_threshold = 3
  enable_sni        = true

  tags = {
    Name = "${var.project}-public-api-health"
  }
}

resource "aws_sns_topic" "alarms_us_east_1" {
  provider = aws.us_east_1
  name     = "${var.project}-alarms-us-east-1"
}

resource "aws_sns_topic_subscription" "email_us_east_1" {
  provider  = aws.us_east_1
  for_each  = toset(var.alert_emails)
  topic_arn = aws_sns_topic.alarms_us_east_1.arn
  protocol  = "email"
  endpoint  = each.value
}

# HealthCheckStatus is 1 (healthy) or 0 (unhealthy) per Route 53's checker
# consensus. evaluation_periods=1 is enough — Route 53 already requires
# failure_threshold consecutive failed probes before the metric flips.
resource "aws_cloudwatch_metric_alarm" "public_api_unreachable" {
  provider            = aws.us_east_1
  alarm_name          = "${var.project}-public-api-unreachable"
  alarm_description   = "External check failed: the public CloudFront URL's /api/v1/health/ready is unreachable or degraded, probed from outside AWS by Route 53."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HealthCheckStatus"
  namespace           = "AWS/Route53"
  period              = 60
  statistic           = "Minimum"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms_us_east_1.arn]
  ok_actions          = [aws_sns_topic.alarms_us_east_1.arn]

  dimensions = {
    HealthCheckId = aws_route53_health_check.public_api.id
  }
}
