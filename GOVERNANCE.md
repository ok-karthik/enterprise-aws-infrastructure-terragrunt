# 🏛️ Platform Governance & Compliance

This document outlines the operational guardrails and compliance standards enforced across the Enterprise AWS Platform.

## 🏷️ Tagging Policy
Mandatory tags are enforced at the Plan JSON level via OPA (Open Policy Agent). Any resource missing these tags will fail the CI/CD pipeline.

| Tag | Required | Purpose |
| :--- | :--- | :--- |
| `Environment` | Yes | Cost allocation and environment isolation (Dev/Prod) |
| `Project` | Yes | Project grouping for unified billing |
| `Service` | Yes | Identifies the specific functional component |
| `ManagedBy` | Yes | Set to `Terragrunt` to identify IaC resources |
| `CostCenter` | Optional | Internal department billing |

## 🛡️ Security Architecture

### Identity & Access (IAM)
- **Zero-Key Pipeline**: No AWS IAM Users or static Access Keys are used. All CI/CD deployments use short-lived **OIDC tokens** via GitHub Actions.
- **Least Privilege**: Deployment roles are strictly scoped to the specific AWS region and account required for the module.

### Encryption
- **At Rest**: KMS encryption is mandatory for all S3 buckets, RDS instances, and EBS volumes.
- **In Transit**: TLS 1.2+ is enforced for all API endpoints.

## 🚦 Change Management (GitHub)

### 🛡️ Recommended GitHub Branch Protection Rules
To ensure the integrity of the `main` branch, the following **GitHub UI settings** (Settings → Branches → Add rule) should be configured:

1.  **Branch name pattern**: `main`
2.  **Require a pull request before merging**: Checked.
    - **Require approvals**: 1
3.  **Require status checks to pass before merging**: Checked.
    - **Status checks**: 
        - `🔍 Quality: Lint & Validate`
        - `📝 Plan: dev`
        - `📝 Plan: prod`
        - `⚖️ Security & Governance (OPA/Checkov): dev`
        - `⚖️ Security & Governance (OPA/Checkov): prod`
        - `💰 Cost Analysis (Infracost): dev`
        - `💰 Cost Analysis (Infracost): prod`
4.  **Require conversation resolution before merging**: Checked (ensures all reviewer comments are addressed).
5.  **Restrict deletions**: Checked.

### Blast Radius Mitigation
- **Environment Isolation**: Dev and Prod environments live in separate VPCs (and ideally separate AWS accounts).
- **Parallel Validation**: All modules are planned and validated in parallel to catch cross-module dependencies early.

## 📜 Compliance Auditing
- **CloudTrail**: Enabled globally for all infrastructure changes.
- **Trivy/Checkov**: Continuous scanning for known vulnerabilities and misconfigurations in HCL.
- **License Compliance**: Automated verification that all local modules include a standard open-source LICENSE, preventing legal risk and vendor lock-in.
