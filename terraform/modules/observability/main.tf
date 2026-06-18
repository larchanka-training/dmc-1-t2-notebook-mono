# Observability: CloudWatch alarms on the prod stack (ALB / ECS / RDS), an SNS
# topic that fans alarms out to email, and a single at-a-glance dashboard.
#
# Philosophy: the system should notice trouble before users do. None of the
# sibling teams (T1/T3) ship alarms — this is the prod-readiness gap we close.
# Everything here is metadata/metrics only; no application data leaves the box.

data "aws_region" "current" {}

# --- SNS topic + (optional) email subscription ---------------------------

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

# Email subscription is created only when an address is supplied. Empty string
# (unset GitHub variable) → topic exists but no subscription; wire it up later.
# Note: email subscriptions must be confirmed via the link AWS emails on create.
resource "aws_sns_topic_subscription" "email" {
  count     = var.alerts_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alerts_email
}

locals {
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# --- ALB alarms -----------------------------------------------------------

# Application is returning 5xx to clients — a user-visible failure spike.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.project}-alb-target-5xx"
  alarm_description   = "API is returning 5xx responses through the ALB."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  dimensions          = { LoadBalancer = var.alb_arn_suffix }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 10
  period              = 300
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching" # no traffic = no errors
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# No healthy task behind the ALB — the API is effectively down.
resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  alarm_name        = "${var.project}-alb-unhealthy-hosts"
  alarm_description = "One or more API tasks are failing ALB health checks."
  namespace         = "AWS/ApplicationELB"
  metric_name       = "UnHealthyHostCount"
  statistic         = "Maximum"
  dimensions = {
    TargetGroup  = var.api_target_group_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  period              = 60
  evaluation_periods  = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# --- ECS alarms -----------------------------------------------------------

# Sustained high CPU above the autoscaler's target — likely hitting max capacity.
resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  alarm_name        = "${var.project}-ecs-cpu-high"
  alarm_description = "API ECS service CPU is sustained high (autoscaler may be at max)."
  namespace         = "AWS/ECS"
  metric_name       = "CPUUtilization"
  statistic         = "Average"
  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 85
  period              = 300
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  alarm_name        = "${var.project}-ecs-memory-high"
  alarm_description = "API ECS service memory is sustained high."
  namespace         = "AWS/ECS"
  metric_name       = "MemoryUtilization"
  statistic         = "Average"
  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 85
  period              = 300
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# --- RDS alarms -----------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project}-rds-cpu-high"
  alarm_description   = "RDS CPU is sustained high."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  dimensions          = { DBInstanceIdentifier = var.db_instance_identifier }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 85
  period              = 300
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# Disk is filling up — risk of a full-disk outage (storage autoscaling helps,
# but this still warns if it can't keep up or is capped).
resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${var.project}-rds-free-storage-low"
  alarm_description   = "RDS free storage is running low."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  dimensions          = { DBInstanceIdentifier = var.db_instance_identifier }
  comparison_operator = "LessThanThreshold"
  threshold           = var.rds_free_storage_threshold_bytes
  period              = 300
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.project}-rds-connections-high"
  alarm_description   = "RDS connection count is unusually high."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Average"
  dimensions          = { DBInstanceIdentifier = var.db_instance_identifier }
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.rds_max_connections
  period              = 300
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# --- Dashboard: one window on prod health --------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-prod"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB — requests & latency"
          region = data.aws_region.current.name
          view   = "timeSeries"
          period = 300
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, { stat = "Average", yAxis = "right" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB — 4xx / 5xx"
          region = data.aws_region.current.name
          view   = "timeSeries"
          period = 300
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS — CPU & memory"
          region = data.aws_region.current.name
          view   = "timeSeries"
          period = 300
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name, { stat = "Average" }],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name, { stat = "Average" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "RDS — CPU, connections & free storage"
          region = data.aws_region.current.name
          view   = "timeSeries"
          period = 300
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", var.db_instance_identifier, { stat = "Average" }],
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.db_instance_identifier, { stat = "Average" }],
            ["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", var.db_instance_identifier, { stat = "Average", yAxis = "right" }]
          ]
        }
      }
    ]
  })
}
