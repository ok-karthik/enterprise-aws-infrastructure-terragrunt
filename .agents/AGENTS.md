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

### 4. IaC Generation Agent (`.agents/prompts/iac_agent.md`, `.agents/scripts/iac_agent.py`)
*   **Role**: Local, on-demand module scaffolder — turns a natural-language infra request into a
    Terragrunt module change.
*   **Responsibility**:
    1.  Match the request against the golden-path catalog (`.agents/catalog/golden-paths.yaml`) —
        a deterministic keyword match, no LLM call. A catalog hit with a `template` renders a
        pre-vetted, known-compliant module with zero LLM-authored HCL (see `data/s3-encrypted`).
    2.  Uncatalogued requests fall back to `classify_request()` (LLM) + `scaffold_skeleton()`
        (deterministic placeholders) + `generate_diff()` (LLM, diff-only, guided by an
        auto-extracted policy digest — `build_policy_digest()` — so the model sees the actual
        `policies/terraform/*.rego` rules and `.checkov.yaml` suppressions up front).
    3.  Every diff — template or LLM-generated — passes an independent `semantic_audit()` review
        (the Policy Auditor persona, #2 above) before the validation ladder runs, catching things
        `terraform validate`/OPA/Checkov can't (over-broad IAM, wrong CIDR, etc.).
    4.  Validation ladder mirrors `smoke-test.sh` plus OPA/Checkov/Trivy, in a generate → audit →
        validate → retry loop, feeding the failing tool's own output back as the fix prompt.
*   **Directives**: Diff-only output, scoped to one module per run. Never pushes and never runs
    `terragrunt apply` — commits locally to a new branch and stops for human review. Designed to work
    with cheap/fast models (e.g. Gemini Flash, or a fully local Ollama model via `--provider ollama`)
    because retrieval, scaffolding, policy awareness, and correctness-checking are pushed onto
    deterministic tooling and a curated catalog, not the model's own knowledge.
*   **Usage**: `python3 .agents/scripts/iac_agent.py --request "..." --env dev --region eu-central-1
    [--skip-plan]` (`--skip-plan` runs static-only checks when no AWS credentials are configured).
    Regression-check classification with `python3 .agents/scripts/iac_agent_eval.py` (see
    `.agents/eval/fixtures.yaml`) — safe to run without any API key, since catalog fixtures are
    fully offline and LLM fixtures skip cleanly when no provider is configured.
*   **Roadmap**: see `PLAN.md` at the repo root for the fuller vision (drift-to-diff, ChatOps
    trigger, cost-aware generation, Backstage/IDP integration, etc.).
