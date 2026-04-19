include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  # get_repo_root() is a Terragrunt built-in that always resolves correctly
  # regardless of how deep this module is in the directory tree
  source = "${get_repo_root()}/infrastructure-modules/eks"
}

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env      = local.env_vars.locals.env
  cluster_name = local.env_vars.locals.cluster_name

  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  aws_region  = local.region_vars.locals.aws_region
}

dependency "vpc" {
  config_path = "../../network/vpc"

  mock_outputs = {
    vpc_id          = "vpc-12345678"
    private_subnets = ["subnet-12345678", "subnet-87654321"]
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]
}

inputs = {
  cluster_name       = local.cluster_name
  kubernetes_version = "1.30"

  vpc_id     = dependency.vpc.outputs.vpc_id
  subnet_ids = dependency.vpc.outputs.private_subnets

  # Node Group Scaling
  min_size     = 1
  max_size     = 3
  desired_size = 1

  # NOTICE: Instance types and Spot capacity are now managed centrally by the wrapper!
  
  tags = {
    Project     = "Infrastructure-Automation"
    Environment = title(local.env)  # title() capitalizes first letter: dev→Dev, prod→Prod
  }
}