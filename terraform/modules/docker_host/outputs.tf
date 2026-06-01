output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.this.id
}

output "public_ip" {
  description = "Публичный IPv4 (для preview-URL и SSH-секретов)."
  value       = aws_instance.this.public_ip
}

output "security_group_id" {
  description = "ID security-group (используется для идемпотентного поиска инстанса)."
  value       = aws_security_group.this.id
}

output "security_group_name" {
  description = "Имя SG — стабильный идентификатор окружения (под текущие права)."
  value       = aws_security_group.this.name
}
