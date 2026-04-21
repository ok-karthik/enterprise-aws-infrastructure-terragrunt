# Common configuration for VPC modules across all environments.

terraform {
  source = "${get_repo_root()}/infrastructure-modules/network/vpc"
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
  cluster_name = local.cluster_name
  
  # Standard subnet layout - Dynamic AZs based on region
  azs             = ["${local.aws_region}a", "${local.aws_region}b", "${local.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24"]
  
  # --- COST OPTIMIZATION: Dynamic NAT ---
  enable_nat_gateway = local.env_vars.locals.enable_nat_gateway
  single_nat_gateway = true

  tags = {
    Project     = "Infrastructure-Automation"
    Environment = title(local.env)
  }
}
