terraform {
  backend "s3" {
    bucket = "dmc-1-t2-notebook-terraform-state"
    key    = "cloud/terraform.tfstate"
    region = "eu-north-1"
    # Terraform 1.10+ native S3 locking (lock file next to the state).
    # No DynamoDB table required. Separate state key from prod/preview so the
    # cloud-native stack never touches the live EC2 prod state.
    use_lockfile = true
    encrypt      = true
  }
}
