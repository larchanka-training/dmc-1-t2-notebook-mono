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
  # Совпадает с уже существующим Name-тегом прод-EC2 → apply не даёт churn.
  name_tag = "TARDIS-T2-prod"
  # ВАЖНО: должно совпадать с description существующего SG, который создал
  # старый CLI-workflow. description у aws_security_group — immutable (ForceNew):
  # любое расхождение → Terraform пересоздаёт SG (а его нельзя удалить, пока он
  # привязан к живому EC2). Поэтому держим ровно как в legacy.
  description   = "jsnotes-t2 prod: SSH + HTTP"
  ingress_ports = [22, 80]
}
