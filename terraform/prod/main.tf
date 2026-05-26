provider "aws" {
  region = var.aws_region
}

# Прод-хост: один долгоживущий EC2 + SG. Если в стейте его ещё нет, но в AWS
# уже есть инстанс (создан старой императивной версией infra-prod.yml) —
# workflow выполняет `terraform import` ДО `apply`, чтобы не пересоздавать
# работающий прод.
module "host" {
  source = "../modules/docker_host"

  name           = var.name
  instance_type  = var.instance_type
  ssh_public_key = var.ssh_public_key
  description    = "jsnotes-t2 prod docker host (SSH + HTTP)"
  ingress_ports  = [22, 80]
}
