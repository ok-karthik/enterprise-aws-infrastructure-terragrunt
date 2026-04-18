include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../infrastructure-modules/vpc"
}

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.env
  cluster_name = local.env_vars.locals.cluster_name

  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  aws_region  = local.region_vars.locals.aws_region
}

inputs = {
  name         = "main-vpc-${local.env}"
  cidr         = "10.0.0.0/16"
  cluster_name = local.cluster_name
  
  azs             = ["${local.aws_region}a", "${local.aws_region}b", "${local.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24"]

  enable_nat_gateway  = true
  single_nat_gateway  = true

  # NOTICE: Tagging is now handled automatically by the wrapper module!
  tags = {
    Project     = "Infrastructure-Automation"
    Environment = local.env
  }
}
