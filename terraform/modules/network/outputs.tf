output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (ALB, NAT)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (ECS tasks, RDS)."
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security group for the ALB."
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group for the ECS tasks."
  value       = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  description = "Security group for RDS."
  value       = aws_security_group.rds.id
}
