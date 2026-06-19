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

output "private_route_table_id" {
  description = "Private route table ID (for associating an S3 gateway VPC endpoint)."
  value       = aws_route_table.private.id
}

output "bastion_security_group_id" {
  description = "Security group for the SSM bastion (null when create_bastion = false)."
  value       = one(aws_security_group.bastion[*].id)
}
