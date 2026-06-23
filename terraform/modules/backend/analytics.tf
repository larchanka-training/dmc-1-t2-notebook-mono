# Product analytics: CloudWatch metric filters + dashboard.
#
# Four structured-log events emitted by the API (via structlog JSON) are
# promoted to CloudWatch metrics so they can be graphed without a log query:
#   notebook_created  — POST /api/v1/notebooks succeeded
#   cell_executed     — code cell run (success path)
#   ai_request        — LLM generation request dispatched
#   execution_error   — cell execution returned an error
#
# Log pattern: structlog writes { "event": "<name>", ... } JSON to stdout;
# the awslogs driver ships it to aws_cloudwatch_log_group.api (main.tf).
# Metric filters extract the `event` field and increment a counter.
#
# Cost: metric filters are free (up to 10/log group); the dashboard is
# $3/month per dashboard.

locals {
  # event key (matches structlog `event=`) → CloudWatch metric name
  analytics_events = {
    notebook_created = "NotebookCreated"
    cell_executed    = "CellExecuted"
    ai_request       = "AIRequest"
    execution_error  = "ExecutionError"
  }

  analytics_namespace = "JSNotebook/Events"
}

# --- Metric filters -------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "analytics" {
  for_each = local.analytics_events

  name           = "${var.project}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.api.name

  # CloudWatch JSON filter: match logs where the top-level "event" field
  # equals the key. structlog serialises every log record as a JSON object,
  # so this reliably captures only the intended event.
  pattern = "{ $.event = \"${each.key}\" }"

  metric_transformation {
    name      = each.value
    namespace = local.analytics_namespace
    value     = "1"
    unit      = "Count"
    # Default value of 0 ensures the metric appears in graphs even on quiet
    # periods, making gaps vs. true-zero distinguishable on the dashboard.
    default_value = 0
  }
}

# --- Dashboard ------------------------------------------------------------
#
# 2 × 2 grid (24-unit wide CloudWatch canvas, each widget 12 × 6):
#   NotebookCreated  |  CellExecuted
#   AIRequest        |  ExecutionError

resource "aws_cloudwatch_dashboard" "analytics" {
  dashboard_name = "${var.project}-analytics"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Notebooks Created"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          view    = "timeSeries"
          metrics = [[local.analytics_namespace, "NotebookCreated"]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Cells Executed"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          view    = "timeSeries"
          metrics = [[local.analytics_namespace, "CellExecuted"]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "AI Requests"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          view    = "timeSeries"
          metrics = [[local.analytics_namespace, "AIRequest"]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "Execution Errors"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          view    = "timeSeries"
          metrics = [[local.analytics_namespace, "ExecutionError"]]
        }
      },
    ]
  })
}
