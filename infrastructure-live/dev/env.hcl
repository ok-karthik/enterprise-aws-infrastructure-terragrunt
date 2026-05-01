locals {
  env          = "dev"
  cluster_name = "main-eks-dev"

  # --- COST OPTIMIZATION: Active Dev ---
  min_size           = 1
  desired_size       = 1
  enable_nat_gateway = true
}
