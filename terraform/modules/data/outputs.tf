output "db_endpoint" {
  description = "RDS endpoint (host:port)."
  value       = aws_db_instance.this.endpoint
}

output "db_instance_id" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.id
}

output "db_name" {
  description = "Database name."
  value       = aws_db_instance.this.db_name
}
