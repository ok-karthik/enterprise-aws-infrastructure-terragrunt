include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "tfr://registry.terraform.io/terraform-aws-modules/eks/aws?version=21.18.0"
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

  # Mock outputs allow 'terragrunt plan' to work even if the VPC isn't applied yet.
  mock_outputs = {
    vpc_id          = "vpc-12345678"
    private_subnets = ["subnet-12345678", "subnet-87654321"]
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]
}

inputs = {
  name    = local.cluster_name
  kubernetes_version = "1.30"

  vpc_id     = dependency.vpc.outputs.vpc_id
  subnet_ids = dependency.vpc.outputs.private_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  compute_config = {
    enabled = false
  }

  eks_managed_node_groups = {
    spot_nodes = {
      instance_types = ["t3.small", "t3.medium"]
      capacity_type  = "SPOT" # This saves 70-90% vs normal price!

      min_size     = 1
      max_size     = 2
      desired_size = 1
    }
  }

  # Useful standard tagging
  tags = {
    Project     = "AWS-Learning"
    Environment = local.env
    ManagedBy   = "Terragrunt"
  }
}