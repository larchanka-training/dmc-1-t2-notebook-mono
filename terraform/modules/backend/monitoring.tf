# Monitoring: SNS topic + CloudWatch alarms on ALB availability signals.
#
# All metrics are in the standard AWS/ApplicationELB namespace — no Container
# Insights required. Three alarms cover the core failure modes:
#   1. unhealthy-hosts  — ECS task failing health check (crash, OOM, bad deploy).
#   2. alb-5xx-errors   — ALB-generated 5xx (502/503/504, e.g. all tasks gone).
#   3. target-5xx-errors — Application-level 5xx (bug in API code).
#   4. high-latency     — p95 > 5 s (DB saturation, blocking calls).
#
# ok_actions mirrors alarm_actions: "recovered" emails arrive when each alarm
# clears, so on-call knows without having to check the console.
#
# EMAIL SUBSCRIPTION NOTE: SNS email subscriptions require manual confirmation,
# one per address. After the first apply that sets alert_emails, AWS sends a
# confirmation email to each address — click "Confirm subscription" in each to
# activate delivery. Until confirmed, alarms fire to the topic but no email is
# delivered to that address.

resource "aws_sns_topic" "alarms" {
  name = "${var.project}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  for_each  = toset(var.alert_emails)
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]
}

# Fires when ≥1 ECS task fails /api/v1/health (unhealthy_threshold = 3 × 30 s).
# Most sensitive signal: covers crash loops, OOM kills, failed rollouts.
resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  alarm_name          = "${var.project}-alb-unhealthy-hosts"
  alarm_description   = "One or more backend tasks failed the ALB health check (GET /api/v1/health)."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }
}

# Fires when ALB itself generates 5xx (502 Bad Gateway when no tasks are
# available, 503 Service Unavailable, 504 Upstream Timeout).
# threshold=5 absorbs a brief spike during rolling restarts.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.project}-alb-5xx-errors"
  alarm_description   = "ALB is returning HTTP 5xx errors (≥5 in one minute)."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }
}

# Fires when the API application itself returns 5xx (distinct from ALB-own
# errors above). Catches unhandled exceptions and panics in running code.
resource "aws_cloudwatch_metric_alarm" "target_5xx" {
  alarm_name          = "${var.project}-target-5xx-errors"
  alarm_description   = "API is returning HTTP 5xx responses (application errors, ≥5 in one minute)."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }
}

# Fires when API p95 latency exceeds 5 seconds for three consecutive minutes.
# Indicates DB connection pool exhaustion, long-running queries, or GC pressure.
resource "aws_cloudwatch_metric_alarm" "alb_latency" {
  alarm_name          = "${var.project}-alb-high-latency"
  alarm_description   = "API p95 response time exceeded 5 seconds for 3 consecutive minutes."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  extended_statistic  = "p95"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }
}
