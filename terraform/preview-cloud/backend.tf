terraform {
  backend "s3" {
    bucket = "dmc-1-t2-notebook-terraform-state"
    key    = "preview-cloud/terraform.tfstate"
    region = "eu-north-1"
    # Terraform 1.10+ native S3 locking (lock file next to the state); no
    # DynamoDB. Separate state key from cloud (prod) / prod / preview so the
    # preview-cloud shared layer never touches another stack's state.
    use_lockfile = true
    encrypt      = true
  }
}
