output "public_ip" {
  description = "Публичный IP preview-хоста. Идёт в sticky-комментарий PR как Preview URL."
  value       = module.host.public_ip
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = module.host.instance_id
}

output "security_group_id" {
  description = "ID per-PR SG."
  value       = module.host.security_group_id
}

output "preview_url" {
  description = "Готовый Preview URL для коммента в PR (http, без TLS — по решению из docs/preview.md)."
  value       = "http://${module.host.public_ip}/"
}
