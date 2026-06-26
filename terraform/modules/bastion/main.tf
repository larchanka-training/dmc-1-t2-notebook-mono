# Bastion: a minimal EC2 jump host for reaching a private RDS from a developer
# laptop via AWS SSM Session Manager port-forwarding — no SSH key, no open inbound
# ports. Access is IAM-gated (ssm:StartSession) and audited in CloudTrail /
# Session Manager logs. The SSM agent reaches the service over outbound 443, so no
# inbound rule is ever needed.
#
# The module serves both stacks; only the egress path to SSM differs:
#   - prod    — private subnet, assign_public_ip = false, egress via the NAT.
#   - preview — public subnet,  assign_public_ip = true,  egress via the IGW
#               (that VPC has no NAT; a public IP with zero inbound is outbound-only).
#
# Connect (needs the AWS CLI Session Manager plugin), then point pgAdmin at the
# tunnel — see each stack's db_tunnel_command output.

# Latest Amazon Linux 2023 AMI (x86_64) via DescribeImages. AL2023 ships the SSM
# agent preinstalled, so the instance becomes a Session Manager target with no
# user-data bootstrap. Deliberately NOT the SSM public-parameter alias: deploy-user
# lacks ssm:GetParameter (verified against live IAM 2026-06-19) but does have
# ec2:DescribeImages, so the alias lookup would fail at apply. ignore_changes=[ami]
# below pins the resolved AMI so most_recent doesn't churn the instance.
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# Instance role: EC2 assumes it; the managed SSM policy is what lets Session
# Manager register and connect to the instance.
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bastion" {
  name               = "${var.project}-bastion"
  assume_role_policy = data.aws_iam_policy_document.assume.json

  tags = { Name = "${var.project}-bastion" }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "${var.project}-bastion"
  role = aws_iam_role.bastion.name
}

resource "aws_instance" "bastion" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.bastion.name

  # Public IP only where there's no NAT (preview) so the SSM agent reaches the
  # service via the IGW. Still no inbound rules, so this is not an attack surface.
  associate_public_ip_address = var.assign_public_ip

  # IMDSv2-only: block the token-less metadata endpoint (SSRF hardening).
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  # data.aws_ami.most_recent resolves to a newer AL2023 AMI over time; without this,
  # an unrelated later apply would want to destroy+recreate the bastion (a
  # destructive change that the CI apply-guard blocks). Pull a fresh AMI
  # deliberately with `terraform apply -replace` (taint) when actually wanted.
  lifecycle {
    ignore_changes = [ami]
  }

  tags = { Name = "${var.project}-bastion" }
}
