# Enterprise IaC Platform & SRE Agent Registry

This document serves as the comprehensive single source of truth for AI agents (Claude Code, Antigravity, custom scripts) and engineers building, auditing, and maintaining the **Enterprise AWS Platform (Terragrunt)**.

---

## 1. What This Repository Is

A multi-environment AWS Infrastructure-as-Code platform built with **Terragrunt + Terraform**. There is no application code — the "product" is HCL config, reusable Terraform modules, OPA/Rego policies, and the GitHub Actions pipeline that plans/applies them. An autonomous Python "healer" agent auto-remediates failed CI runs, and an on-demand IaC Platform Agent scaffolds and reconciles compliant modules.

### Infrastructure Layout
*   `/infrastructure-live/`: Contains environment-specific configurations (`terragrunt.hcl`) and shared category blueprints (`_envcommon/`).
*   `/infrastructure-modules/`: Custom reusable Terraform modules (`network/vpc`, `compute/eks`). Pure `.tf`, no environment specifics.
*   `/infrastructure-bootstrap/`: Day-0 stack (OIDC provider, IAM roles, S3 state bucket, DynamoDB lock) that bootstraps the backend state.
*   `/policies/terraform/`: Rego-based OPA compliance rules enforced against Terraform plan JSON.
*   `/.agents/`: Catalog, prompts, eval fixtures, SRE policies, and scripts for autonomous agents.

---

## 2. Essential Commands

All tooling is baked into the toolchain container (`.github/docker/Dockerfile`); locally install the equivalents (Terraform `1.15.1`, Terragrunt `1.0.3` pinned in Dockerfile ARGs and `.github/actions/setup-platform/action.yml`).

```bash
# Full local validation suite — compliance, fmt, terragrunt init+validate (dev), tflint.
# This is the pre-commit hook and the CI "smoke test"; run it before pushing.
./infrastructure-live/scripts/smoke-test.sh

# Formatting — MUST cover all four roots or CI fails (see static-analysis action)
terraform fmt -recursive infrastructure-modules infrastructure-live infrastructure-bootstrap policies
terragrunt hcl fmt

# Lint / security / policy
tflint --init && tflint --recursive --format=compact
trivy config . --severity CRITICAL,HIGH --ignorefile .trivyignore --tf-exclude-downloaded-modules
conftest test --policy policies/terraform <plan.json>   # policy runs against plan JSON, not HCL

# Plan/apply a single environment stack (uses run --all across the dependency graph)
cd infrastructure-live/dev && terragrunt run --all plan --non-interactive
cd infrastructure-live/dev && terragrunt run --all apply --non-interactive -auto-approve

# Plan/apply one module only
cd infrastructure-live/dev/eu-central-1/compute/eks && terragrunt plan

# Scaffold a new module manually
./infrastructure-live/scripts/generate-module.sh <category/module-name> [env] [region]

# Install the pre-commit hook (fmt + smoke-test + trivy on every commit)
pre-commit install
```

---

## 3. Architecture: The Terragrunt Inheritance Chain

The core pattern is **strict separation of "blueprint" from "live config"**, kept 100% DRY through a layered `include`/`read_terragrunt_config` chain:

1. **`infrastructure-modules/`** — generic, reusable Terraform (`network/vpc`, `compute/eks`). Pure `.tf`, no environment specifics. Security hardening lives *here* (VPC deny-all NACLs, EKS KMS encryption), not just in CI.

2. **`infrastructure-live/root.hcl`** — the global root included by every leaf. It **generates `provider.tf` and `backend.tf`** at runtime (`generate` blocks) and injects `default_tags` (`Environment`, `Service`, `Project`, `ManagedBy`, `Account`). The S3 backend bucket name and `default_tags` are computed here — do not add provider/backend blocks by hand in modules.

3. **`infrastructure-live/_envcommon/<category>/<module>.hcl`** — the shared blueprint per module type. Sets `terraform.source` (pointing into `infrastructure-modules/` or registry `tfr://`), declares `dependency` blocks (with `mock_outputs` for plan-time), and default `inputs`. Cross-module wiring (EKS → VPC subnets) lives here.

4. **Data files loaded via `find_in_parent_folders`:**
   - `<env>/account.hcl` — `aws_account_id`, `account_name`
   - `<env>/env.hcl` — `env`, `cluster_name`, and cost-scaling knobs (`min_size`, `desired_size`, `enable_nat_gateway`)
   - `<env>/<region>/region.hcl` — `aws_region`

5. **`infrastructure-live/<env>/<region>/<category>/<module>/terragrunt.hcl`** — the leaf. Includes `root` + the matching `_envcommon` file (`expose = true`) and only overrides env-specific values (e.g. dev EKS shrinks `min_size`/`max_size`/`desired_size`).

`path_relative_to_include()` drives naming everywhere (state key, `Service` tag, env detection), so **directory layout is load-bearing** — the `<env>/<region>/<category>/<module>` shape is a contract, not a convention. `dev`/`prod`/`staging` are the only allowed env names and regions must be `eu-*`/`us-*` (enforced by `smoke-test.sh`).

---

## 4. Governance Gates (What Will Block a PR)

These are enforced against the **Terraform plan JSON** in CI (`reusable-terragrunt.yml`), so a change can pass `terraform validate` and still fail here:

- **OPA/Conftest** (`policies/terraform/*.rego`, package `main`):
  - `require_service_tag.rego` — every created/updated resource must carry `Service`, `Environment`, `Project` tags (checked in `tags_all`). The `root.hcl` `default_tags` normally satisfies this; resources that escape provider default tags will fail.
  - `no_legacy_instances.rego` — blocks old instance families (`t2.`, `m3.`, `m4.`, `c3.`, `c4.`).
- **Checkov** — config in `.checkov.yaml`; a curated `skip-check` list documents intentionally accepted findings. Add suppressions there with a comment, don't disable the gate.
- **Trivy** — `CRITICAL,HIGH` fail the build; suppressions go in `.trivyignore`.
- **Infracost** — posts a per-module cost breakdown PR comment (and blocks agent changes exceeding configured budget thresholds).

---

## 5. CI/CD Pipeline

- `terragrunt.yml` — main orchestrator. Static analysis + `dev`/`prod` reusable stacks run in parallel; on push to `main`, `apply-dev` runs then `apply-prod` (gated by a protected GitHub `prod` Environment requiring manual approval).
- `reusable-terragrunt.yml` — per-environment plan → governance (OPA/Checkov/Trivy) → cost analysis. Plans are generated as `tfplan.bin`, converted to `tfplan.json`, uploaded as artifacts, and consumed by the gate jobs.
- Auth is **zero-key OIDC** — jobs assume `vars.AWS_DEV_ROLE_ARN` / `vars.AWS_PROD_ROLE_ARN` via `setup-platform`. No static AWS credentials exist.
- `drift-detection.yml` — nightly matrix over dev/prod; manages one GitHub Issue per env (create/comment/auto-close) and prompts for ChatOps reconciliation.
- `chatops_generator.yml` — listens for `/generate` and `/reconcile` issue/PR comments to trigger automated module authoring and PR creation.
- `pipeline_healer.yml` — triggers on a failed "Terragrunt CI/CD" run and executes `.agents/scripts/healer_runner.py`.

---

## 6. Conventions & Gotchas

- **Never hand-write `provider.tf` or `backend.tf`** — they are generated by `root.hcl`. Editing them has no effect (`if_exists = "overwrite_terragrunt"`).
- When adding a module, create both the blueprint (`_envcommon/.../<m>.hcl` → `terraform.source`) and the leaf `terragrunt.hcl` in each env; don't inline module logic into a live dir.
- `fmt` must pass across `infrastructure-modules`, `infrastructure-live`, `infrastructure-bootstrap`, **and** `policies` — a stray unformatted `.tf`/`.hcl` in any of the four fails Gate 1.
- Rego policies target Rego v1 (`import rego.v1`) and package `main`.
- Cost knobs (spot/scaling) live in `env.hcl`; keep dev cheap (spot, min sizes) — the README's FinOps numbers depend on it.

---

## 7. Agent Registry & Platform Capabilities

### 1. IaC Architect (`.agents/prompts/architect.md`)
*   **Role**: Senior Cloud Infrastructure Architect.
*   **Responsibility**: Writes valid Terraform/Terragrunt HCL.
*   **Directives**: Must use dry-run testing (`-backend=false` init / `terraform validate`) and strictly respect variable declarations under `/infrastructure-live`.

### 2. Policy Auditor (`.agents/prompts/auditor.md`)
*   **Role**: Security & Governance Compliance Officer.
*   **Responsibility**: Performs independent semantic review and automated compliance checks, returning `STATUS: PASSED/FAILED`.
*   **Directives**: Enforces Rego policy checks in `/policies/terraform/`, Checkov/TFLint standards, and semantic sanity checks (no wildcard IAM, no public ingress on DB/SSH ports).

### 3. Pipeline Healer (`.agents/prompts/ci_healer.md`, `.agents/scripts/healer_runner.py`)
*   **Role**: Incident & CI/CD Recovery Specialist.
*   **Responsibility**: Runs automatically on workflow failure (`pipeline_healer.yml`), isolates root cause from GitHub runner logs, auto-resolves provider lock mismatches, or generates a minimal LLM git patch and pushes to the PR branch.
*   **Directives**: Prioritize minimal diffs. Safe directory config and ephemeral container root execution.

### 4. IaC Generation & Platform Agent (`.agents/prompts/iac_agent.md`, `.agents/scripts/iac_agent.py`)
*   **Role**: Autonomous Platform Engineering & SRE Agent — provides self-service infrastructure generation, drift reconciliation, and change-risk governance.
*   **Capabilities**:
    1.  **Golden-Path Catalog** (`.agents/catalog/golden-paths.yaml`): Deterministic keyword matching renders pre-vetted modules (`data-s3-encrypted`, `data-rds-postgres`) with zero LLM-authored HCL.
    2.  **Uncatalogued Requests**: LLM classification (`classify_request`) + deterministic scaffolding (`scaffold_skeleton`) + diff-only generation (`generate_diff`) informed by live Rego/Checkov policy digests (`build_policy_digest`).
    3.  **Semantic Second-Opinion Gate**: Every diff passes independent LLM review via the Policy Auditor persona before validation.
    4.  **Full Validation Ladder**: Offline validation (`-backend=false`), `tflint`, OPA/Conftest, Checkov, Trivy, and Infracost cost threshold gating.
    5.  **Drift-to-Diff Reconciliation** (`--reconcile`): Ingests Terraform plan drift outputs and generates corrective HCL diffs.
    6.  **ChatOps Trigger** (`.github/workflows/chatops_generator.yml`): Responds to `/generate` and `/reconcile` issue comments.
    7.  **Multi-Module Graph Decomposition** (`--graph`): Topologically decomposes multi-service requests (VPC + EKS + RDS) with cross-module dependency injection.
    8.  **Model Context Protocol (MCP) Client** (`.agents/scripts/mcp_client.py`): Direct JSON-RPC doc querying with GitHub raw fallback.
    9.  **Developer Portal / Backstage Integration** (`.agents/backstage/`): Software templates (`s3-bucket.yaml`, `rds-postgres.yaml`), catalog registration, and CLI runner.
    10. **SRE Error-Budget Guardrails** (`.agents/sre/error_budgets.yaml`): Blocks unapproved production proposals when the error budget is below 10%.
    11. **Telemetry & Health Metrics** (`.agents/metrics/runs.jsonl`, `.agents/scripts/iac_agent_metrics.py`): Append-only metrics tracking success rates, ladder failure causes, and high-demand module types.
*   **Usage**:
    ```bash
    # Generate single module (offline dry-run)
    python3 .agents/scripts/iac_agent.py --request "add an S3 bucket for artifacts" --dry-run

    # Multi-module graph decomposition
    python3 .agents/scripts/iac_agent.py --request "stand up VPC and RDS" --graph --dry-run

    # Local Platform HTTP API server
    python3 .agents/scripts/iac_agent.py --serve --port 8000

    # Display health metrics summary
    python3 .agents/scripts/iac_agent.py --metrics-summary

    # Run eval and test suite
    python3 .agents/scripts/iac_agent_eval.py
    python3 -m unittest discover -s .agents/tests
    ```
