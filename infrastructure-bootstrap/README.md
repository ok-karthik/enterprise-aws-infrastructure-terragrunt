# 🚀 Platform Bootstrap Reference

This directory contains the "Pre-CI/CD" infrastructure required to stand up the foundational trust and state management layers. These resources must be applied manually once to enable the automated pipelines.

## 🏗️ Bootstrapping Order

To initialize the enterprise platform, deploy these components in order:

### 1. State Hub
- **Purpose**: Creates the S3 Bucket and DynamoDB table used for Terragrunt remote state locking.
- **Action**: `cd infrastructure-bootstrap/state-hub && terragrunt apply`

### 2. OIDC Identity Trust (Global)
- **Purpose**: Establishes OIDC trust between AWS and GitHub. This allows the CI/CD pipeline to assume IAM roles without using long-lived Access Keys.
- **Action**: `cd infrastructure-live/dev/eu-central-1/security/github-oidc-provider && terragrunt apply`

### 3. CI/CD Permission Layer
- **Purpose**: Creates the IAM Role assumed by the GitHub Actions runners.
- **Action**: `cd infrastructure-live/dev/eu-central-1/security/github-oidc-role && terragrunt apply`

---

## 🔐 Security Note
The OIDC trust is strictly scoped to this specific GitHub repository (`${github_repo_url}`). This follows the **Principle of Least Privilege**, ensuring that only authorized CI/CD runs can modify your production infrastructure.
