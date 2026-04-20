include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/compute/eks.hcl"
  expose = true
}

# Mirroring Dev scaling but with Prod tags
inputs = {
  min_size     = 1
  max_size     = 3
  desired_size = 2 # Slightly higher default for prod parity
  
  # Ensure compliance with Policy-as-Code gates
  tags = {
    Environment = "prod"
    Service     = "kubernetes"
  }
}
