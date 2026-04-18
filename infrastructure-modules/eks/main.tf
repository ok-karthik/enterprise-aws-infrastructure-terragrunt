module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.18.0"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # --- GOVERNANCE: Standard Compute Configuration ---
  # We enforce that all clusters use the new compute config standard.
  compute_config = {
    enabled = false
  }

  # --- GOVERNANCE: Standard Node Groups ---
  # Every cluster in the organization uses Spot Managed Node Groups to save costs.
  eks_managed_node_groups = {
    spot_nodes = {
      instance_types = var.instance_types
      capacity_type  = "SPOT"

      min_size     = var.min_size
      max_size     = var.max_size
      desired_size = var.desired_size
    }
  }

  # --- GOVERNANCE: Mandatory Tagging ---
  tags = merge(
    {
      ManagedBy     = "Terragrunt-Wrapper"
      SecurityLevel = "High"
      K8sAccess     = "IAM-Only"
    },
    var.tags
  )
}
