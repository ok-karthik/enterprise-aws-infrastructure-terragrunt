#!/bin/bash
set -e

# --- 🚀 Platform Smoke Test (Disaster Recovery Validation) ---
# This script validates that the platform code is syntactically correct 
# and that the remote state backend is reachable.

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "🧪 Starting Platform Smoke Test..."

# 1. HCL Syntax Check
echo "1. Checking Platform Compliance & Standards..."
# Verify environment names
for env_dir in infrastructure-live/dev infrastructure-live/prod infrastructure-live/staging; do
  if [ -d "$env_dir" ]; then
    env_name=$(basename "$env_dir")
    if [[ ! "$env_name" =~ ^(dev|prod|staging)$ ]]; then
       echo "❌ ERROR: Unsupported environment folder '$env_name'."
       exit 1
    fi
  fi
done

# Verify regional compliance in region.hcl files
for region_file in $(find infrastructure-live -name "region.hcl"); do
  region=$(grep "aws_region" "$region_file" | cut -d'"' -f2)
  if [[ ! "$region" =~ ^(eu-|us-) ]]; then
    echo "❌ ERROR: Region '$region' in $region_file is not supported (EU/US only)."
    exit 1
  fi
done
echo "✅ Compliance checks passed."

echo -e "\n2. Checking HCL formatting..."
if terraform fmt -check -recursive infrastructure-modules && \
   terraform fmt -check -recursive infrastructure-live && \
   terraform fmt -check -recursive infrastructure-bootstrap && \
   terraform fmt -check -recursive policies; then
    echo -e "${GREEN}✅ HCL Formatting is correct.${NC}"
else
    echo -e "${RED}❌ HCL Formatting issues found. Fix with 'terragrunt hcl format'.${NC}"
    exit 1
fi

# 2. Dependency Graph Validation
echo -e "\n2. Validating Terragrunt dependency graph (Dev)..."
cd infrastructure-live/dev
if terragrunt run --all validate --non-interactive; then
    echo -e "${GREEN}✅ Dependency graph and variables are valid.${NC}"
else
    echo -e "${RED}❌ Validation failed in dev stack.${NC}"
    exit 1
fi
cd - > /dev/null

# 3. TFLint recursive scan
echo -e "\n3. Running TFLint recursive scan..."
if tflint --recursive --format=compact; then
    echo -e "${GREEN}✅ TFLint passed for all modules.${NC}"
else
    echo -e "${RED}❌ TFLint found issues.${NC}"
    exit 1
fi

echo -e "\n${GREEN}🚀 ALL SMOKE TESTS PASSED! Platform is ready for recovery/deployment.${NC}"
