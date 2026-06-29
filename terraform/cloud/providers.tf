provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# us-east-1 alias — required later for the CloudFront ACM certificate, which
# must live in us-east-1 regardless of the project region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}

# Cost-allocation / ownership tags stamped on every resource via default_tags.
# `Team` is the key dimension for per-team cost attribution in the shared
# account (Cost Explorer / Budgets / Cost Categories). After the first apply,
# activate Team/Environment/Project as cost-allocation tags in the management
# account — they are not retroactive. See the PR runbook.
locals {
  common_tags = {
    Team        = "t2"
    Project     = var.project
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
