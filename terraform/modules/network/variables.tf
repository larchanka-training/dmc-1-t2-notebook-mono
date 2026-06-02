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
