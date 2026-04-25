#!/bin/bash
set -e

# --- 🚀 Platform Bootstrap Automation ---
# This script automates the deployment of foundational OIDC trust layers.

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}⚖️ Starting Platform Bootstrap...${NC}"

# 1. Deploy OIDC Provider
echo -e "\n${BLUE}1. Deploying OIDC Provider...${NC}"
cd dev/_global/security/github-oidc-provider
terragrunt apply -auto-approve
cd - > /dev/null

# 2. Deploy OIDC Role
echo -e "\n${BLUE}2. Deploying OIDC Role...${NC}"
cd dev/_global/security/github-oidc-role
terragrunt apply -auto-approve

# 3. Extract Role ARN
ROLE_ARN=$(terragrunt output -raw arn 2>/dev/null || echo "ERROR_FETCHING_ARN")
cd - > /dev/null

echo -e "\n${GREEN}✅ Infrastructure Bootstrap Complete!${NC}"

# 4. Instructions for GitHub
echo -e "\n${BLUE}------------------------------------------------------------${NC}"
echo -e "${BLUE}📋 NEXT STEPS: Configure GitHub Variables${NC}"
echo -e "${BLUE}------------------------------------------------------------${NC}"
echo -e "To enable the automated pipeline, you must add the following variable to GitHub:"
echo -e "\n${GREEN}Variable Name:  AWS_DEV_ROLE_ARN${NC}"
echo -e "${GREEN}Variable Value: $ROLE_ARN${NC}"
echo -e "\nGo to: ${BLUE}https://github.com/${GITHUB_REPOSITORY:-<your-repo>}/settings/variables/actions${NC}"
echo -e "${BLUE}------------------------------------------------------------${NC}"
