# Private path to Amazon Bedrock.
#
# An interface VPC endpoint (PrivateLink) for the bedrock-runtime API. Invoke /
# Converse calls from the ECS tasks reach Bedrock over the AWS private network
# instead of egressing through the NAT gateway to the public endpoint — which
# satisfies the "private internal network only" requirement (issue #113).
#
# With private_dns_enabled = true the standard hostname
# bedrock-runtime.<region>.amazonaws.com resolves to this endpoint inside the
# VPC, so the application needs no code or config change to use it.

data "aws_region" "current" {}

# Endpoint firewall: HTTPS in, from the ECS tasks only.
resource "aws_security_group" "bedrock_endpoint" {
  name        = "${var.project}-bedrock-endpoint-sg"
  description = "Bedrock interface endpoint: HTTPS from the ECS tasks only"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "HTTPS from ECS tasks"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  # No egress rule: an interface-endpoint ENI never initiates connections — it
  # only sends responses, which security groups allow statefully regardless. Omitting
  # egress keeps this SG least-privilege (the endpoint can't reach anything outbound).

  tags = { Name = "${var.project}-bedrock-endpoint-sg" }
}

resource "aws_vpc_endpoint" "bedrock_runtime" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.bedrock_endpoint.id]
  private_dns_enabled = true

  tags = { Name = "${var.project}-bedrock-runtime" }
}
