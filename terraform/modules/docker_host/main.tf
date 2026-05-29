# Reusable модуль: EC2-хост с предустановленным Docker + SSH-ключом ubuntu.
#
# Намеренные ограничения под текущие права deploy-user:
# - Не пользуемся `tags` на ресурсах (ec2:CreateTags теперь разрешён, но
#   идемпотентность всё равно держится на имени SG — это переживёт сброс прав).
# - SSH-ключ зашивается через user-data, IAM instance-profile не используется
#   (ECR-логин делает CI-раннер и пробрасывает токен по SSH в docker login).

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "this" {
  name        = "${var.name}-sg"
  description = var.description
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = var.ingress_ports
    content {
      description = "tcp/${ingress.value}"
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Не затираем теги, навешанные на легаси-SG вне Terraform.
  lifecycle {
    ignore_changes = [
      tags,
      tags_all,
    ]
  }
}

locals {
  user_data = <<-EOT
    #!/bin/bash
    set -euo pipefail
    install -d -m 700 -o ubuntu -g ubuntu /home/ubuntu/.ssh
    echo "${var.ssh_public_key}" >> /home/ubuntu/.ssh/authorized_keys
    chown ubuntu:ubuntu /home/ubuntu/.ssh/authorized_keys
    chmod 600 /home/ubuntu/.ssh/authorized_keys
    install -d -m 755 -o ubuntu -g ubuntu /home/ubuntu/app

    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ca-certificates curl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    usermod -aG docker ubuntu
  EOT
}

resource "aws_instance" "this" {
  ami                         = data.aws_ami.ubuntu_2204.id
  instance_type               = var.instance_type
  subnet_id                   = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = true
  user_data                   = local.user_data

  # AMI-id меняется при обновлении базовой Ubuntu — это не повод пересоздавать
  # уже работающий хост. user_data тоже фиксируем, чтобы рефакторинг скрипта не
  # триггерил replace. tags игнорируем, чтобы не затирать теги, которые могли
  # быть навешаны на легаси-инстанс вне Terraform.
  lifecycle {
    ignore_changes = [
      ami,
      user_data,
      tags,
      tags_all,
    ]
  }
}
