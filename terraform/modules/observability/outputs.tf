output "alerts_topic_arn" {
  description = "ARN of the SNS topic alarms publish to."
  value       = aws_sns_topic.alerts.arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard name."
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}
