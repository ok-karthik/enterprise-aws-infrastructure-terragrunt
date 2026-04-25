#!/bin/bash
# 🏗️ Terragrunt Module Generator
# Usage: ./generate-module.sh <category/module-name> [env] [region]

set -e

MODULE_PATH=$1
ENV=${2:-dev}
REGION=${3:-eu-central-1}

if [ -z "$MODULE_PATH" ]; then
    echo "❌ Error: Module path (e.g., storage/s3) is required."
    echo "Usage: $0 <category/module-name> [env] [region]"
    exit 1
fi

TARGET_DIR="infrastructure-live/$ENV/$REGION/$MODULE_PATH"

if [ -d "$TARGET_DIR" ]; then
    echo "⚠️ Warning: Module already exists at $TARGET_DIR"
    exit 0
fi

echo "🚀 Scaffolding new module: $MODULE_PATH in $ENV ($REGION)..."

mkdir -p "$TARGET_DIR"

# Generate terragrunt.hcl template
cat <<EOF > "$TARGET_DIR/terragrunt.hcl"
# 🧬 Terragrunt configuration for $MODULE_PATH
# This module inherits from the root and envcommon layers.

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path = "\${get_repo_root()}/infrastructure-live/_envcommon/$MODULE_PATH.hcl"
}

# Add module-specific inputs here if they differ from _envcommon
inputs = {
  # tags = {
  #   CustomTag = "Value"
  # }
}
EOF

echo "✅ Success! Created $TARGET_DIR/terragrunt.hcl"
echo "👉 Don't forget to create the corresponding _envcommon/$MODULE_PATH.hcl if it doesn't exist."
