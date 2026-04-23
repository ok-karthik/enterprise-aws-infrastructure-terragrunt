include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/network/vpc.hcl"
  expose = true
}

# Production VPC might use a different CIDR range to avoid overlapping with Dev
inputs = {
  cidr = "10.1.0.0/16"

}
