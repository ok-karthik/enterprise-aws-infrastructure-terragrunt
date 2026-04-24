# 🏗️ Enterprise AWS Platform (Terragrunt & Terraform)

[![Terragrunt](https://img.shields.io/badge/Infrastructure-Terragrunt-blue)](https://terragrunt.gruntwork.io/)
[![Terraform](https://img.shields.io/badge/IAC-Terraform-blueviolet)](https://www.terraform.io/)
[![Security](https://img.shields.io/badge/Security-Checkov%2BTrivy-success)](https://github.com/bridgecrewio/checkov)
[![Licence](https://img.shields.io/badge/License-MIT-gray.svg)](LICENSE)

A production-grade, multi-environment AWS platform architecture designed for scalability, security governance, and FinOps efficiency. This project demonstrates **Staff Engineer level patterns** in Infrastructure-as-Code (IaC) management, focusing on modularity, policy-driven security, and automated delivery.

---

## 🏛️ Project Architecture

This platform follows a **Hierarchical Blueprint Pattern** using Terragrunt. It separates the "Generic Blueprint Library" from the "Live Environment Implementation," ensuring 100% DRY (Don't Repeat Yourself) code.

### 🧬 Repository Structure

```text
.
├── infrastructure-modules/      # 📦 Blueprint Library (Reusable Terraform)
│   ├── network/vpc/            # - Standardized VPC & Subnets
│   ├── compute/eks/            # - Production-Grade EKS
│   └── data/s3/                # - Durable Object Storage
│
├── infrastructure-live/         # 🚀 Deployment Hub (Environment Config)
│   ├── _envcommon/             # 🧬 Centralized DRY inheritance layer
│   ├── dev/ (Regions)          # Sandbox Environment
│   │   └── eu-central-1/
│   │       ├── network/vpc/    #   - terragrunt.hcl
│   │       └── compute/eks/    #   - terragrunt.hcl
│   └── prod/ (Regions)         # Production Environment
│       └── eu-central-1/
│           ├── network/vpc/    #   - terragrunt.hcl
│           └── compute/eks/    #   - terragrunt.hcl
│
└── infrastructure-bootstrap/   # 🗝️ Foundation (OIDC & Remote State Hub)
```

---

## 🚀 The Automated Platform (CI/CD)

The core of this platform is a sophisticated **5-Stage Pipeline** that transitions infrastructure from code to production with multiple security and cost gates.

### 🚀 Dual-Gate Pipeline Architecture
The platform utilizes a **Modular CI/CD Orchestration** model built on GitHub Reusable Workflows and Composite Actions. This ensures a DRY (Don't Repeat Yourself) pipeline that is both fast and extremely secure.

1.  **Gate 1: High-Speed Static Analysis (HCL)**
    *   **Goal**: Immediate feedback for developers.
    *   **Tools**: TFLint (Quality), Trivy (IaC Security), Checkov (Basic HCL misconfigs).
    *   **Scope**: Scans the raw code before any AWS credentials are required.

2.  **Gate 2: High-Precision Governance (JSON)**
    *   **Goal**: Final safety check before deployment.
    *   **Tools**: **Checkov (JSON Plan)**, **OPA (Rego laws)**.
    *   **Scope**: Scans the actual Terraform Plan JSON after variables and logic are resolved, catching "hidden" security leaks.

> [!NOTE]
> **Modular Design:** All tool installations and AWS logins are centralized in a **Local Composite Action**, ensuring that our CI/CD maintenance overhead is near zero.

#### 💰 Sample PR Cost Audit
The pipeline posts a consolidated report to the PR. Below is a high-fidelity representation of the Infracost output:

```text
Project: .../compute/eks/tfplan.json
 Name                                             Monthly Qty  Unit         Monthly Cost
 module.eks.aws_eks_cluster.this[0]                       730  hours              $73.00
 module.eks.module.eks_managed_node_group["spot"]       1,460  hours              $13.43
 module.eks.module.kms.aws_kms_key.this[0]                  1  months              $1.00

 Project total                                                                    $92.19
 OVERALL TOTAL                                                                    $92.19
```

> [!TIP]
> **View a live example of our automated PR audits:**
> [Live PR Review & Cost Analysis #7](https://github.com/ok-karthik/enterprise-aws-platform-terragrunt/pull/7#issuecomment-2804241908)

4.  **🚀 Parallel Planning**: Simultaneous planning across all environment modules for rapid engineering feedback.
5.  **🚦 Manual Approval Gates**: Environment-protected deployment using GitHub Environments. No code reaches `Dev` or `Prod` without explicit manual review in the Actions UI.

> [!TIP]
> **View our professional CI/CD orchestration:**
>
> <p align="center">
>   <img src=".github/assets/cicd-pipeline-flow.png" width="900" alt="Consolidated CI/CD Pipeline Flow">
> </p>

---

## 📊 PR-Driven FinOps & Governance

Every Pull Request automatically triggers a comprehensive audit across all environments. This ensures 100% visibility into cost impacts and architectural changes before code reaches production.

### 🛡️ Automated Quality Gates
- **Cost Estimation (Infracost)**: High-fidelity monthly cost impact per environment.
- **Change Auditing (tf-summarize)**: Human-readable tables of every resource being Added, Deleted, or Modified.
- **Security Guardrails**: Automated Checkov and OPA (Open Policy Agent) scans run on every plan.

### 📝 Sample PR Report
The pipeline posts a consolidated report for each environment (**dev** and **prod**) to the PR conversation. This enables side-by-side comparison of environment-specific costs and resource changes.

<details><summary><b>View Sample PR Report Structure</b></summary>

#### 📊 Infrastructure Change Summary (dev)
> 💡 This report summarizes resource changes and estimated cost impact for the **dev** environment.

📂 **Module: compute/eks**
```text
+----------+-----------------------------------------------------------+
|  CHANGE  |                         RESOURCE                          |
+----------+-----------------------------------------------------------+
| add (37) | module.eks.aws_eks_cluster.this[0]                        |
|          | module.eks.module.eks_managed_node_group["spot_nodes"]... |
+----------+-----------------------------------------------------------+
```

#### 💰 Cost Estimate (dev)
```text
 OVERALL TOTAL                                             $124.71 
```
</details>

---

## 🔐 Security & Governance

- **OIDC Authentication**: Zero long-lived AWS keys. All deployments use short-lived, trust-based OIDC tokens (OpenID Connect).
- **Least Privilege**: The CI/CD role is strictly scoped to specific IAM actions and repository branches.

### ⚖️ Governance & Policy (OPA)
While tools like Checkov handle general security, we use **Open Policy Agent (OPA)** via **Conftest** to enforce custom organizational "laws." These are checked against the Terraform Plan JSON before any deployment.

*   **🏷️ Mandatory Tagging**: Enforces `Service`, `Environment`, and `Project` tags on all resources to ensure 100% cost-allocation visibility.
*   **💻 Instance Modernization**: Prevents the use of legacy AWS instance types (e.g., `t2.*`), forcing teams to use modern Nitro-based hardware for better price-performance.
*   **🔌 Sequential Dependency Gates**: Automated validation using `terragrunt run-all` to respect the infrastructure dependency graph (e.g., VPC must be ready before EKS).

> [!TIP]
> **Learning Rego:** Our policies are written in **Rego**, a declarative language optimized for complex logic. Check out the [policies/terraform](policies/terraform) directory to see how we programmatically define these enterprise guardrails.

- **Hierarchical Governance**: Global policies are enforced at the `root.hcl` and `_envcommon` layers, ensuring that every subsystem inherits standard tagging and security settings.

---

## 💰 FinOps & Efficiency

- **Automated PR Cost Auditing**: Every infrastructure change is priced using Infracost before approval, ensuring "Cost as Code" visibility for all engineers.
- **Spot Instances**: In the `dev` environment, EKS managed node groups are configured for Spot capacity to reduce costs by ~70-90%.
- **GP3 Storage Mandate**: Automated governance ensures all EBS volumes are provisioned as `gp3` (Amazon Linux 2023), optimizing for both performance and price.
- **Lifecycle Management**: A dedicated **Manual Teardown Workflow** allows for surgical removal of resources in non-production environments to avoid "hidden" costs when stacks are not in use.
- **Tagging Policy**: Standardized tagging (`Project`, `Environment`, `Service`) is enforced at the module wrapper level to ensure 100% visibility in AWS Cost Explorer.

---

## 🛠️ Getting Started

### 📋 Prerequisites
Before you begin, ensure you have the following tools installed:
- [Terraform](https://developer.hashicorp.com/terraform/downloads) (v1.5+)
- [Terragrunt](https://terragrunt.gruntwork.io/docs/getting-started/quick-start/) (v0.50+)
- [TFLint](https://github.com/terraform-linters/tflint)
- [Checkov](https://www.checkov.io/1.Getting%20Started/Installation.html)
- [Infracost](https://www.infracost.io/docs/)
- [Conftest](https://www.conftest.dev/) (for OPA policy testing)

### 💻 Local Development Setup
1.  **Clone the Repo**:
    ```bash
    git clone https://github.com/ok-karthik/enterprise-aws-platform-terragrunt.git
    cd enterprise-aws-platform-terragrunt
    ```
2.  **Initialize TFLint**:
    ```bash
    tflint --init
    ```
3.  **Local Validation**:
    Run the Gate 1 checks locally to catch issues early:
    ```bash
    tflint --recursive
    checkov -d .
    ```

## 🛠️ Deployment Instructions

1.  **Bootstrap**: See [infrastructure-bootstrap/README.md](infrastructure-bootstrap/README.md) for initial Day-0 setup.
2.  **Development**: Merge your infrastructure changes to a feature branch. Review the `Consolidated Report` in the PR.
3.  **Production**: Merge to `main`. The pipeline will pause for your manual approval before applying changes to the `prod` environment.

## 🧠 Development Approach

Selective AI assistance was used for accelerating documentation and validating CI/CD patterns. All architectural decisions, directory structure, and engineering tradeoffs were designed and reviewed independently to ensure enterprise-grade stability.

---

## 🤝 Contributing
Contributions are welcome! Please ensure any new modules include:
- TFLint validation
- Checkov-compliant HCL
- OPA-compliant tagging

---

---

## 📸 Platform Screenshots

### 🚦 Production Deployment Gate
The platform utilizes **GitHub Environments** to enforce manual approval gates before code reaches `prod`. This ensures that even with 100% automated validation, human oversight is maintained for critical infrastructure changes.

<p align="center">
  <img src=".github/assets/github-actions-manual-approval.png" width="900" alt="GitHub Actions Manual Approval Gate">
</p>

---

*This platform is maintained as a showcase of senior Platform Engineering patterns. For inquiries, please reach out to [ok-karthik](https://github.com/ok-karthik).*

