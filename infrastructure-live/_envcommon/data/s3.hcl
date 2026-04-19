# Common configuration for S3 modules.

terraform {
  source = "tfr://registry.terraform.io/terraform-aws-modules/s3-bucket/aws?version=4.6.0"
}

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.env
}

inputs = {
  bucket_name = "tg-learning-bucket-${local.env}-${get_aws_account_id()}" # Using account ID for uniqueness
  
  tags = {
    Environment = title(local.env)
    Service     = "data-s3"
  }
}
