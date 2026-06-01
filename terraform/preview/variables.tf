variable "aws_region" {
  description = "AWS-регион."
  type        = string
  default     = "eu-north-1"
}

variable "instance_type" {
  description = "Тип EC2 для preview (бюджетный по умолчанию)."
  type        = string
  default     = "t3.micro"
}

variable "ssh_public_key" {
  description = "Публичная половина SSH-ключа. Reuse приватной половины из secret SSH_PRIVATE_KEY — тот же ключ, что и для прода."
  type        = string
}

variable "pr_number" {
  description = "Номер PR. Задаётся из preview.yml (-var). Используется в Name-теге; имя SG берётся из terraform.workspace, чтобы совпадало с workspace_key_prefix."
  type        = string
}
