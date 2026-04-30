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

  # 4. Define the Backend Configuration
  # This is used for BOTH bucket creation and file generation.
  backend_bucket = "tg-state-${local.account_id}-${local.account_alias}-${local.aws_region}"
  backend_key    = "${path_relative_to_include()}/terraform.tfstate"
}


# --- GENERATION: Provider ---
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

# --- GENERATION: Backend ---
# We use a manual 'generate' block to ensure 100% control over the HCL.
# This prevents Terragrunt 1.0.1 from leaking internal security keys into the file.
generate "backend" {
  path      = "backend.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  backend "s3" {
    bucket         = "${local.backend_bucket}"
    key            = "${local.backend_key}"
    region         = "${local.aws_region}"
    encrypt        = true
    use_lockfile   = true
  }
}
EOF
}

# --- BUCKET MANAGEMENT ---
# We use 'remote_state' WITHOUT 'generate' to handle bucket creation and hardening.
remote_state {
  backend = "s3"
  config = {
    bucket         = local.backend_bucket
    key            = local.backend_key
    region         = local.aws_region
    encrypt        = true
    use_lockfile   = true

    # --- SECURITY: Hardening the State Bucket ---
    # These are used by Terragrunt for bucket creation but are NOT passed to 'generate'.
    skip_bucket_versioning         = false
    access_block_public_acls       = true
    access_block_public_policy     = true
    ignore_public_acls      = true
    restrict_public_buckets = true
  }
}