output "public_ip" {
  description = "Публичный IP прод-хоста. В deploy.yml используется через secret SSH_HOST."
  value       = module.host.public_ip
}

output "instance_id" {
  description = "EC2 instance ID прода."
  value       = module.host.instance_id
}

output "security_group_id" {
  description = "ID прод-SG."
  value       = module.host.security_group_id
}

output "security_group_name" {
  description = "Имя прод-SG (стабильный идентификатор)."
  value       = module.host.security_group_name
}
