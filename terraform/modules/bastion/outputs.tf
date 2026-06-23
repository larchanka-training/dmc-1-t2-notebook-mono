output "instance_id" {
  description = "Bastion instance ID — the --target of `aws ssm start-session`."
  value       = aws_instance.bastion.id
}
