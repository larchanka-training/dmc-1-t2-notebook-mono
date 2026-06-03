provider "aws" {
  region = var.aws_region
}

# us-east-1 alias — required for the CloudFront ACM certificate (must live in
# us-east-1 regardless of the project region). Used once preview gets a domain.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
