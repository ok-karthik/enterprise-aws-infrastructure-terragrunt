include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/compute/eks.hcl"
  expose = true
}

# Override scaling or types if needed for dev
inputs = {
  min_size     = 1
  max_size     = 2
  desired_size = 1
}
