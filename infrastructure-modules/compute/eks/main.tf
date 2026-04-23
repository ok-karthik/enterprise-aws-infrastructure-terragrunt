terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.18.0"

  # --- v21 API: 'cluster_name' was renamed to 'name', 'cluster_version' → 'kubernetes_version' ---
  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  # --- GOVERNANCE: Standard Node Groups ---
  # Every cluster in the organization uses Spot Managed Node Groups to save costs.
  eks_managed_node_groups = {
    spot_nodes = {
      ami_type       = "AL2_x86_64"
      instance_types = var.instance_types
      capacity_type  = "SPOT"

      min_size     = var.min_size
      max_size     = var.max_size
      desired_size = var.desired_size

      # Simplify: Use the native disk_size attribute which the module 
      # handles correctly for managed node groups.
      use_custom_launch_template = false
      disk_size                  = 20
    }
  }

  # --- GOVERNANCE: Mandatory Tagging ---
  tags = merge(
    {
      ManagedBy     = "Terragrunt-Wrapper"
      SecurityLevel = "High"
      K8sAccess     = "IAM-Only"
      Service       = "compute-eks" # Required by FinOps tag policy
    },
    var.tags
  )
}
