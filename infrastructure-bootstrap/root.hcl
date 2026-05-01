# This file generates the backend.tf and provider.tf automatically
# for every child module.

locals {
  # 1. Load the variables from your file structure
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))

  # 2. Extract them into simple local variables
  aws_region    = local.region_vars.locals.aws_region
  env           = local.env_vars.locals.env
  account_alias = local.account_vars.locals.account_name

  # 3. Get the Account ID dynamically (No need to hardcode this one if you don't want to)
  account_id = get_aws_account_id()
}

# Generate an AWS provider block
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.aws_region}"

  # Only allow this to run on the correct account (Safety Feature!)
  allowed_account_ids = ["${local.account_id}"]

  default_tags {
    tags = {
      Environment = "${title(local.env)}"
      ManagedBy   = "Terragrunt"
      Account     = "${local.account_alias}"
    }
  }
}
EOF
}

# Configure S3 State Backend automatically
remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    # CHANGE THIS to a unique bucket name for your state
    bucket       = "tg-state-${local.account_id}-${local.account_alias}-${local.aws_region}"
    key          = "${path_relative_to_include()}/terraform.tfstate"
    region       = "${local.aws_region}"
    encrypt      = true
    use_lockfile = true
  }
}
