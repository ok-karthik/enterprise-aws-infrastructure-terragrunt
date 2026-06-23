# Enterprise IaC SRE Agent Registry

This directory contains framework-agnostic definition files for AI agents designed to build, audit, and heal the **Enterprise AWS Platform (Terragrunt)**.

---

## Project Context Reference
These parameters must be loaded or understood by any tool (Claude Code, Antigravity, or custom Python scripts) representing these agents:
*   **Infrastructure Layout**:
    *   `/infrastructure-live/`: Contains environment-specific configurations (terragrunt.hcl).
    *   `/infrastructure-modules/`: Custom reusable Terraform modules.
*   **Compliance Rule Directory**: `/policies/terraform/` (rego-based OPA rules).
*   **Cloud Provider**: AWS (specifically target multi-account topologies).

---

## Agent Registry

### 1. IaC Architect (`.agents/prompts/architect.md`)
*   **Role**: Senior Cloud Infrastructure Architect.
*   **Responsibility**: Writes valid Terraform/Terragrunt HCL.
*   **Directives**: Must use dry-run testing (localstack / tf validate) and strictly respect variable declarations under `/infrastructure-live`.

### 2. Policy Auditor (`.agents/prompts/auditor.md`)
*   **Role**: Security & Governance Compliance Officer.
*   **Responsibility**: Runs automated compliance checks and reports STATUS: PASSED/FAILED.
*   **Directives**: Must enforce Rego policy checks in `/policies/terraform/` and Checkov/TFLint standards.

### 3. Pipeline Healer (`.agents/prompts/ci_healer.md`)
*   **Role**: Incident & CI/CD Recovery Specialist.
*   **Responsibility**: Run on pipeline failure, analyze runner outputs, isolate the fault, and submit git PRs with the code fix.
*   **Directives**: Prioritize minimal diffs. If the failure is a dependency issue or policy breach, consult the `Policy Auditor` guidelines to fix it correctly.
