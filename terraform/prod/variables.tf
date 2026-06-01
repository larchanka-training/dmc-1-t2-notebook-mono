variable "aws_region" {
  description = "AWS-регион."
  type        = string
  default     = "eu-north-1"
}

variable "name" {
  description = "Префикс ресурсов прод-окружения. Должен совпадать с существующим (SG=<name>-sg), иначе terraform пересоздаст SG."
  type        = string
  default     = "jsnotes-t2-prod"
}

variable "instance_type" {
  description = "Тип EC2 для прода."
  type        = string
  default     = "t3.micro"
}

variable "ssh_public_key" {
  description = "Публичная половина SSH-ключа (TF_VAR_ssh_public_key в CI). Используется только при первом создании хоста — на уже работающем хосте user_data игнорируется (см. lifecycle в модуле)."
  type        = string
}
