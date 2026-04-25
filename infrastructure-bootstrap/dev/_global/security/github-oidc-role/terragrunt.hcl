include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "tfr://registry.terraform.io/terraform-aws-modules/iam/aws//modules/iam-github-oidc-role?version=5.39.0"
}

# Ensure the OIDC Provider (the trust bridge) is created before the role
dependency "oidc_provider" {
  config_path = "../github-oidc-provider"

  mock_outputs = {
    arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]
}

locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  account_name = local.account_vars.locals.account_name
  env          = local.env_vars.locals.env

  # The GitHub repository that is allowed to assume this role
  github_repo = "ok-karthik/enterprise-aws-infrastructure-terragrunt"
}

inputs = {
  name = "github-actions-oidc-role"

  subjects = ["repo:${local.github_repo}:*"]

  policies = {
    AdministratorAccess = "arn:aws:iam::aws:policy/AdministratorAccess"
  }

  # These tags will be merged with the default_tags from root.hcl
  tags = {
    Project = "Infrastructure-Automation"
    Role    = "github-actions-oidc"
  }
}
