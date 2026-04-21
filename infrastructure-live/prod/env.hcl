locals {
  env          = "prod"
  cluster_name = "main-eks-prod"

  # --- COST OPTIMIZATION: Dormant Prod ---
  min_size           = 0
  desired_size       = 0
  enable_nat_gateway = false
}