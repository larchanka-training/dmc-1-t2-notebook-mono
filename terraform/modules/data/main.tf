# Data: managed PostgreSQL (RDS) in the private subnets, reachable only from the
# ECS security group, plus the DATABASE_URL secret value (the secret container
# itself is created in the backend module; the value is set here once the RDS
# endpoint exists).
#
# Hardening (better than T1's RDS): storage encrypted, automated backups,
# deletion protection, a final snapshot on destroy.

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.project}-db-subnet-group" }
}

# special = false keeps the password URL-safe (no @ : / # in the DATABASE_URL).
# The generated value feeds both aws_db_instance.password (below) and the
# DATABASE_URL/migration secrets, so a regeneration updates the RDS master
# password and the secrets in the same apply — they cannot diverge into a lockout.
resource "random_password" "db" {
  length  = 24
  special = false
}

resource "aws_db_instance" "this" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.rds_security_group_id]

  multi_az                = var.multi_az
  backup_retention_period = var.backup_retention_days

  # Storage autoscaling: null leaves a fixed-size disk; a value lets RDS grow
  # allocated_storage toward it as the disk fills (prevents a full-disk outage).
  max_allocated_storage = var.max_allocated_storage

  # Query-level load visibility (Performance Insights) + OS-level Enhanced
  # Monitoring. The monitoring role is only created when monitoring_interval > 0.
  performance_insights_enabled = var.performance_insights_enabled
  monitoring_interval          = var.monitoring_interval
  monitoring_role_arn          = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  # Apply modifications online (no reboot) right away instead of deferring to the
  # maintenance window — so Multi-AZ/PI/monitoring actually take effect on apply.
  apply_immediately = var.apply_immediately

  # Production safety: protect against accidental deletion and keep a final
  # snapshot. To `terraform destroy` you must first set deletion_protection=false.
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-db-final"

  tags = { Name = "${var.project}-db" }

  # Enhanced Monitoring: RDS validates MonitoringRoleArn at modify time, so the
  # role's managed policy must already be ATTACHED — otherwise the modify can
  # race the attachment (IAM eventual consistency) and fail. depends_on tolerates
  # the empty list when monitoring is disabled (count = 0).
  depends_on = [aws_iam_role_policy_attachment.rds_monitoring]
}

# Enhanced Monitoring publishes OS-level metrics (CPU, memory, disk I/O) to
# CloudWatch via this role, which RDS assumes. Created only when monitoring is on.
data "aws_iam_policy_document" "rds_monitoring_assume" {
  count = var.monitoring_interval > 0 ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_monitoring" {
  count              = var.monitoring_interval > 0 ? 1 : 0
  name               = "${var.project}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.rds_monitoring_assume[0].json
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count      = var.monitoring_interval > 0 ? 1 : 0
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# Set the DATABASE_URL value now that the endpoint is known. The endpoint
# already includes the port (host:5432).
resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = var.database_url_secret_arn
  secret_string = "postgresql://${var.db_username}:${random_password.db.result}@${aws_db_instance.this.endpoint}/${var.db_name}"
}

# Set the Liquibase migration connection (JDBC url + creds, as JSON keys the
# migration task reads via LIQUIBASE_COMMAND_URL/_USERNAME/_PASSWORD).
resource "aws_secretsmanager_secret_version" "db_migration" {
  secret_id = var.migration_secret_arn
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    url      = "jdbc:postgresql://${aws_db_instance.this.endpoint}/${var.db_name}"
  })
}
