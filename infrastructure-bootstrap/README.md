# 🚀 Platform Bootstrap Reference

This directory contains the "Pre-CI/CD" infrastructure required to stand up the foundational trust and state management layers. These resources must be applied manually once to enable the automated pipelines.

## 🏗️ Bootstrapping Order

To initialize the enterprise platform, you can use the **guided automation script** or follow the manual steps below:

### ⚡ Guided Bootstrap (Recommended)
We provide a script that automates the deployment and provides direct instructions for GitHub:
```bash
cd infrastructure-bootstrap
chmod +x bootstrap.sh
./bootstrap.sh
```

---

### 📖 Manual Bootstrap Steps
If you prefer to run things manually, deploy these components in order:

### 1. OIDC Identity Trust (Global)
- **Purpose**: Establishes OIDC trust between AWS and GitHub. This allows the CI/CD pipeline to assume IAM roles without using long-lived Access Keys.
- **Action**:
  ```bash
  cd infrastructure-bootstrap/dev/_global/security/github-oidc-provider
  terragrunt apply
  ```

### 2. CI/CD Permission Layer
- **Purpose**: Creates the IAM Role assumed by the GitHub Actions runners.
- **Action**:
  ```bash
  cd infrastructure-bootstrap/dev/_global/security/github-oidc-role
  terragrunt apply
  ```

### 3. GitHub Action Variables (CRITICAL)
Once the infrastructure is applied, you must register the Role ARNs in GitHub to enable the automated pipeline.

1.  Navigate to your repository on GitHub.
2.  Go to **Settings** -> **Actions** -> **Variables** -> **Repository**.
3.  Add the following **Repository Variables**:
    *   `AWS_DEV_ROLE_ARN`: The ARN of the role created in Step 2.
    *   `AWS_PROD_ROLE_ARN`: (If applicable) The ARN for the production role.
    *   `AWS_REGION`: Your primary deployment region (e.g., `eu-central-1`).

---

## 🔐 Why Repository Variables?
We use **Repository Variables** instead of Environment Variables for the Role ARNs because:
1.  **Automatic Planning**: It allows `terragrunt plan` to run automatically on Pull Requests without being blocked by environment approval gates.
2.  **Scalability**: New environments can be added by simply adding a new variable (e.g., `AWS_STAGING_ROLE_ARN`) without modifying workflow YAML.

---

## 🛠️ Toolchain & CI/CD Architecture
The CI/CD pipeline relies on a custom, pre-packaged Docker container (`ghcr.io/ok-karthik/infrastructure-toolchain`) to ensure absolute consistency across all runs.
*   **Node.js 24 Standard**: All internal GitHub Actions (`checkout`, `upload-artifact`, etc.) have been modernized to use Node.js 24, permanently resolving runtime deprecation warnings.
*   **Runner Compatibility**: To prevent `EACCES` (Permission Denied) errors when the GitHub runner writes to the workspace (`/__w/_temp`), the container runs with explicit root privileges (`options: --user root` in the workflow) while the underlying image is highly optimized with `--no-install-recommends`.

---

## 🔐 Security Note
The OIDC trust is strictly scoped to this specific GitHub repository. This follows the **Principle of Least Privilege**, ensuring that only authorized CI/CD runs can modify your production infrastructure.
