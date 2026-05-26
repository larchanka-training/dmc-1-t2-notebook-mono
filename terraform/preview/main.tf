provider "aws" {
  region = var.aws_region
}

# Per-PR окружение: workspace = "pr-<N>", каждый PR держит свой state и свои
# EC2 + SG. Имя SG строится из terraform.workspace, чтобы оно автоматически
# совпадало с границей workspace и не зависело от того, как нас вызвали.
module "host" {
  source = "../modules/docker_host"

  name           = "jsnotes-preview-${terraform.workspace}"
  instance_type  = var.instance_type
  ssh_public_key = var.ssh_public_key
  description    = "jsnotes-t2 preview env for ${terraform.workspace} (PR #${var.pr_number})"
  ingress_ports  = [22, 80]
}
