terraform {
  backend "s3" {
    bucket = "dmc-1-t2-notebook-terraform-state"
    # workspace_key_prefix: каждый workspace (pr-<N>) получит свой ключ
    # вида preview-workspaces/pr-<N>/terraform.tfstate.
    key                  = "preview/terraform.tfstate"
    workspace_key_prefix = "preview-workspaces"
    region               = "eu-north-1"
    use_lockfile         = true
    encrypt              = true
  }
}
