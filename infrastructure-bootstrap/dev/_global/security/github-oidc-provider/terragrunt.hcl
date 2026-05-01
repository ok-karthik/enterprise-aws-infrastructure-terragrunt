include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "tfr://registry.terraform.io/terraform-aws-modules/iam/aws//modules/iam-github-oidc-provider?version=5.39.0"
}

# The module defaults to GitHub (https://token.actions.githubusercontent.com)
# and the standard audience (sts.amazonaws.com).
# No additional inputs are strictly required for the basic setup.
inputs = {
  tags = {
    Name = "github-oidc-provider"
  }
}
