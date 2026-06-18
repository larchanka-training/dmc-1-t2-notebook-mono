output "db_endpoint" {
  description = "RDS endpoint (host:port)."
  value       = aws_db_instance.this.endpoint
}

output "db_instance_id" {
  description = "RDS resource ID (db-XXXX form, from aws_db_instance.id)."
  value       = aws_db_instance.this.id
}

# The human identifier (e.g. jsnotes-t2-db) — this, NOT .id, is the value
# CloudWatch's DBInstanceIdentifier dimension expects. aws_db_instance.id is the
# db-XXXX resource ID, which does not match any CloudWatch metric series.
output "db_instance_identifier" {
  description = "RDS instance identifier (CloudWatch DBInstanceIdentifier dimension)."
  value       = aws_db_instance.this.identifier
}

output "db_name" {
  description = "Database name."
  value       = aws_db_instance.this.db_name
}
