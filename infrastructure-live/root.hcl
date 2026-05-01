# This file generates the backend.tf and provider.tf automatically
# for every child module.

locals {
  # 1. Load the variables from your file structure
  env = split("/", path_relative_to_include())[0]

  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  # 2. Extract them into simple local variables
  aws_region    = local.region_vars.locals.aws_region
  account_alias = local.account_vars.locals.account_name
  cluster_name  = local.env_vars.locals.cluster_name

  # 3. Get the Account ID dynamically
  account_id = get_aws_account_id()
}


# Generate an AWS provider block
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.aws_region}"
  allowed_account_ids = ["${local.account_id}"]

  default_tags {
    tags = {
      Environment = "${title(local.env)}"
      ManagedBy   = "Terragrunt"
      Account     = "${local.account_alias}"
      Project     = "enterprise-aws-platform"
      Service     = "${path_relative_to_include()}"
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
    # --- Standard S3 Backend Config ---
    # These are standard keys recognized by both Terragrunt and Terraform.
    bucket       = "tg-state-${local.account_id}-${local.account_alias}-${local.aws_region}"
    key          = "${path_relative_to_include()}/terraform.tfstate"
    region       = "${local.aws_region}"
    encrypt      = true
    use_lockfile = true

    # --- SECURITY: S3 Bucket Tags ---
    # Terragrunt uses these for bucket creation and filters them from backend.tf.
    s3_bucket_tags = {
      ManagedBy   = "Terragrunt"
      Security    = "Hardened"
      Environment = title(local.env)
    }

    # NOTE: Terragrunt 1.0.x enables S3 Versioning by default for auto-created buckets.
    # To avoid 'Invalid argument' errors during init, we rely on Terragrunt's
    # internal defaults for Block Public Access which are enforced during
    # the bucket creation handshake.
  }
}
