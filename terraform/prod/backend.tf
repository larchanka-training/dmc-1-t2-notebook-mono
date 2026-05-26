terraform {
  backend "s3" {
    bucket = "jsnotes-t2-tfstate"
    key    = "prod/terraform.tfstate"
    region = "eu-north-1"
    # Terraform 1.10+: native S3 locking (lock-файл рядом со state).
    # DynamoDB-таблица под locking больше не требуется.
    use_lockfile = true
    encrypt      = true
  }
}
