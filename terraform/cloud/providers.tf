provider "aws" {
  region = var.aws_region
}

# us-east-1 alias — required later for the CloudFront ACM certificate, which
# must live in us-east-1 regardless of the project region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
