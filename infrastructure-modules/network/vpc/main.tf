terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.6.0"

  name = var.name
  cidr = var.cidr

  azs             = var.azs
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets

  enable_nat_gateway = var.enable_nat_gateway
  single_nat_gateway = var.single_nat_gateway

  # --- AUTOMATION: EKS Subnet Tagging ---
  # These tags are required for the EKS Load Balancer Controller to discover subnets.
  # We handle this automatically so the user doesn't have to remember them.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = merge(
    {
      "kubernetes.io/role/internal-elb" = 1
    },
    var.cluster_name != "" ? { "kubernetes.io/cluster/${var.cluster_name}" = "shared" } : {}
  )

  # --- GOVERNANCE: Mandatory Tagging ---
  # We merge user-provided tags with our mandatory organizational tags.
  tags = merge(
    {
      ManagedBy     = "Terragrunt-Wrapper"
      SecurityLevel = "High"
      Compliance    = "SOC2-Prototype"
      Service       = "network-vpc" # Required by FinOps tag policy
    },
    var.tags
  )

  # --- SECURITY: VPC Flow Logs ---
  # Enables auditing of all network traffic within the VPC.
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
  flow_log_max_aggregation_interval    = 60
}
