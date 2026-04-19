include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  # Using the public terraform-aws-modules/s3-bucket module
  # A local wrapper can be added to infrastructure-modules/s3/ in future if needed
  source = "tfr://registry.terraform.io/terraform-aws-modules/s3-bucket/aws?version=4.6.0"
}

locals {
  # YOU MUST LOAD IT HERE AGAIN to use it in this file
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.env
}

inputs = {
  # This is the only place we define values!
  bucket_name = "tg-learning-bucket-${local.env}-12345" # Must be globally unique

  tags = {
    Project     = "App Logs"
    Environment = title(local.env)  # title() capitalizes first letter: dev→Dev, prod→Prod
    Service     = "data-s3" # Required by FinOps tag policy
  }
}