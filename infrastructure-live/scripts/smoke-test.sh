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
echo -e "\n1. Checking HCL formatting..."
if find infrastructure-modules infrastructure-live infrastructure-bootstrap policies -name "*.hcl" -not -path "*/.*" -print0 | xargs -0 terragrunt hcl format --check; then
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
