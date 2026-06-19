variable "project" {
  description = "Resource name prefix (e.g. jsnotes-t2)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

# Two-tier layout across two AZs (a/b):
#   public   10.0.1.0/24  10.0.2.0/24   — internet-facing (ALB, NAT gateway)
#   private  10.0.11.0/24 10.0.12.0/24  — egress via NAT (ECS tasks, RDS)
variable "public_subnet_cidrs" {
  description = "CIDRs for the two public subnets (AZ a, b)."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDRs for the two private subnets (AZ a, b)."
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "api_port" {
  description = "Container port the API listens on (ALB → ECS)."
  type        = number
  default     = 8000
}

variable "create_nat" {
  description = "Create a NAT gateway (+ Elastic IP) for private-subnet internet egress. Set false to rely on VPC endpoints instead (no EIP needed)."
  type        = bool
  default     = true
}

variable "create_bastion" {
  description = "Create the bastion security group and open RDS 5432 to it (the EC2 jump host itself lives in modules/bastion). Used for SSM port-forwarding to RDS from a developer laptop. Default off; each root stack opts in by passing its own create_bastion (also default off), so a caller that doesn't pass it through is unaffected."
  type        = bool
  default     = false
}
