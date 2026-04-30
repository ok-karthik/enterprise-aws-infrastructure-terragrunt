# This file generates the backend.tf and provider.tf automatically
# for every child module.

locals {
  # 1. Load the variables from your file structure
  # WE NO LONGER RELY ON env.hcl FOR IDENTITY - WE USE THE FOLDER PATH!
  # This makes the code completely "Clonable".
  env = split("/", path_relative_to_include())[0]

  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  # 2. Extract them into simple local variables
  aws_region    = local.region_vars.locals.aws_region
  account_alias = local.account_vars.locals.account_name
  cluster_name  = local.env_vars.locals.cluster_name # Stored in env.hcl for unique naming

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
    # CHANGE THIS to a unique bucket name for your state
    bucket       = "tg-state-${local.account_id}-${local.account_alias}-${local.aws_region}"
    key          = "${path_relative_to_include()}/terraform.tfstate"
    region       = "${local.aws_region}"
    encrypt      = true
    use_lockfile = true

    # --- SECURITY: Hardening the State Bucket ---
    # These 'access_' keys are native to Terragrunt for bucket creation.
    # They are automatically filtered out from the generated backend.tf.
    skip_bucket_versioning         = false
    access_block_public_acls       = true
    access_block_public_policy     = true
    access_ignore_public_acls      = true
    access_restrict_public_buckets = true
  }
}