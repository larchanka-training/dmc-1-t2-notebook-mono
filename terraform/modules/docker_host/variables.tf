variable "name" {
  description = "Базовое имя ресурсов (используется в group-name SG и в Name-теге, если когда-то появятся ec2:CreateTags). Должно быть уникально в пределах региона."
  type        = string
}

variable "instance_type" {
  description = "Тип EC2-инстанса"
  type        = string
  default     = "t3.micro"
}

variable "ssh_public_key" {
  description = "Публичная половина SSH-ключа, которая будет положена в ~ubuntu/.ssh/authorized_keys через user-data."
  type        = string
  sensitive   = false
}

variable "ingress_ports" {
  description = "Какие TCP-порты открыть с 0.0.0.0/0. По умолчанию 22 (SSH) и 80 (HTTP)."
  type        = list(number)
  default     = [22, 80]
}

variable "description" {
  description = "Человекочитаемое описание SG."
  type        = string
  default     = "jsnotes-t2 docker host (SSH + HTTP)"
}

variable "name_tag" {
  description = "Значение Name-тега EC2 (как видно в консоли AWS). Развязан с var.name, потому что var.name задаёт group-name SG (immutable/ForceNew), а Name-тег можно менять in-place. По умолчанию = var.name."
  type        = string
  default     = null
}
