include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path   = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/data/s3.hcl"
  expose = true
}

# Unique bucket name suffix for prod logs
inputs = {
  bucket_name = "tg-learning-bucket-prod-app-logs-7788"
  
  tags = {
    Project = "App Logs"
  }
}