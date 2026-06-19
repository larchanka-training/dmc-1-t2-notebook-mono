variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "subnet_id" {
  description = "Subnet to place the bastion in. Use a private subnet where NAT exists (prod); use a public subnet with assign_public_ip = true where there is no NAT (preview), so the SSM agent can still reach the service via the internet gateway."
  type        = string
}

variable "assign_public_ip" {
  description = "Give the bastion a public IP. Needed only when it sits in a public subnet of a NAT-less VPC (preview) so the SSM agent's outbound 443 reaches the service via the IGW. With no inbound SG rules a public IP is not an attack surface. Keep false in private subnets (prod)."
  type        = bool
  default     = false
}

variable "security_group_id" {
  description = "Bastion security group (no inbound; egress 443 for SSM + 5432 to RDS). Created in the network module."
  type        = string
}

variable "instance_type" {
  description = "Bastion instance type. t3.nano is enough to host an SSM port-forwarding tunnel."
  type        = string
  default     = "t3.nano"
}
