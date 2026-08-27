# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A multi-environment AWS Infrastructure-as-Code platform built with **Terragrunt + Terraform**. There is no application code — the "product" is HCL config, reusable Terraform modules, OPA/Rego policies, and the GitHub Actions pipeline that plans/applies them. An experimental Python "healer" agent auto-remediates failed CI runs.

## Commands

All tooling is baked into the toolchain container (`.github/docker/Dockerfile`); locally install the equivalents (see README "Prerequisites"). Terraform `1.15.1`, Terragrunt `1.0.3` — versions are pinned in the Dockerfile ARGs and `.github/actions/setup-platform/action.yml`, both carrying `# renovate:` comments that keep them in sync.

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

# Scaffold a new module
./infrastructure-live/scripts/generate-module.sh <module-name>

# Install the pre-commit hook (fmt + smoke-test + trivy on every commit)
pre-commit install
```

There is no unit-test suite — validation *is* `terraform validate` + policy gates. The OPA policies in `policies/terraform/` are the closest thing to tests; exercise them with `conftest test` against a generated `tfplan.json`.

## Architecture: the Terragrunt inheritance chain

The core pattern is **strict separation of "blueprint" from "live config"**, kept 100% DRY through a layered `include`/`read_terragrunt_config` chain. To understand any live module you must read *all* of these layers, because a single leaf `terragrunt.hcl` is often ~10 lines and inherits everything else:

1. **`infrastructure-modules/`** — generic, reusable Terraform (`network/vpc`, `compute/eks`). Pure `.tf`, no environment specifics. Security hardening lives *here* (VPC deny-all NACLs, EKS KMS encryption), not just in CI.

2. **`infrastructure-live/root.hcl`** — the global root included by every leaf. It **generates `provider.tf` and `backend.tf`** at runtime (`generate` blocks) and injects `default_tags` (`Environment`, `Service`, `Project`, `ManagedBy`, `Account`). The S3 backend bucket name and `default_tags` are computed here — do not add provider/backend blocks by hand in modules.

3. **`infrastructure-live/_envcommon/<category>/<module>.hcl`** — the shared blueprint per module type. Sets `terraform.source` (pointing into `infrastructure-modules/`), declares `dependency` blocks (with `mock_outputs` for plan-time), and default `inputs`. Cross-module wiring (EKS → VPC subnets) lives here.

4. **Data files loaded via `find_in_parent_folders`:**
   - `<env>/account.hcl` — `aws_account_id`, `account_name`
   - `<env>/env.hcl` — `env`, `cluster_name`, and cost-scaling knobs (`min_size`, `desired_size`, `enable_nat_gateway`)
   - `<env>/<region>/region.hcl` — `aws_region`

5. **`infrastructure-live/<env>/<region>/<category>/<module>/terragrunt.hcl`** — the leaf. Includes `root` + the matching `_envcommon` file (`expose = true`) and only overrides env-specific values (e.g. dev EKS shrinks `min_size`/`max_size`/`desired_size`).

`path_relative_to_include()` drives naming everywhere (state key, `Service` tag, env detection), so **directory layout is load-bearing** — the `<env>/<region>/<category>/<module>` shape is a contract, not a convention. `dev`/`prod`/`staging` are the only allowed env names and regions must be `eu-*`/`us-*` (enforced by `smoke-test.sh`).

**`infrastructure-bootstrap/`** is the separate Day-0 stack (OIDC provider, IAM roles, S3 state bucket, DynamoDB lock) that must exist before `infrastructure-live` can deploy. It bootstraps the very backend the live stacks depend on.

## Governance gates (what will block a PR)

These are enforced against the **Terraform plan JSON** in CI (`reusable-terragrunt.yml`), so a change can pass `terraform validate` and still fail here:

- **OPA/Conftest** (`policies/terraform/*.rego`, package `main`):
  - `require_service_tag.rego` — every created/updated resource must carry `Service`, `Environment`, `Project` tags (checked in `tags_all`). The `root.hcl` `default_tags` normally satisfies this; resources that escape provider default tags will fail.
  - `no_legacy_instances.rego` — blocks old instance families (`t2.`, `m3.`, `m4.`, `c3.`, `c4.`).
- **Checkov** — config in `.checkov.yaml`; a curated `skip-check` list documents intentionally accepted findings. Add suppressions there with a comment, don't disable the gate.
- **Trivy** — `CRITICAL,HIGH` fail the build; suppressions go in `.trivyignore`.
- **Infracost** — posts a per-module cost breakdown PR comment (non-blocking).

## CI/CD pipeline

- `terragrunt.yml` — main orchestrator. Static analysis + `dev`/`prod` reusable stacks run in parallel; on push to `main`, `apply-dev` runs then `apply-prod` (gated by a protected GitHub `prod` Environment requiring manual approval).
- `reusable-terragrunt.yml` — per-environment plan → governance (OPA/Checkov/Trivy) → cost analysis. Plans are generated as `tfplan.bin`, converted to `tfplan.json`, uploaded as artifacts, and consumed by the gate jobs.
- Auth is **zero-key OIDC** — jobs assume `vars.AWS_DEV_ROLE_ARN` / `vars.AWS_PROD_ROLE_ARN` via `setup-platform`. No static AWS credentials exist.
- `drift-detection.yml` — nightly matrix over dev/prod; manages one GitHub Issue per env (create/comment/auto-close).
- All jobs run inside `ghcr.io/ok-karthik/infrastructure-toolchain:latest` (published by `publish-toolchain.yml`).

## The Healer agent (`.agents/`)

`pipeline_healer.yml` triggers on a **failed** "Terragrunt CI/CD" run and executes `.agents/scripts/healer_runner.py` (always pulling the latest `.agents` from `main` first). The script:
1. Downloads logs for the *failed jobs only* (GitHub Jobs API) to stay under the Groq token limit.
2. If it detects a provider-lock mismatch, runs `terragrunt/terraform init -upgrade -backend=false` on every active `.terraform.lock.hcl` and commits the result — temporarily mocking `get_aws_account_id()` in HCL so parsing works without AWS creds, then `git checkout`-reverting those files.
3. Otherwise sends logs + a project file tree to a Groq LLM (`llama-3.3-70b-versatile`), extracts a `git diff` from the response, `git apply`s it, and pushes the fix to the PR branch.

Agent role definitions live in `.agents/prompts/` and `.agents/AGENTS.md`. When editing the healer, note it runs in an ephemeral root container: system-wide `safe.directory` config and `pip install --break-system-packages` are load-bearing, not accidental.

## Conventions & gotchas

- **Never hand-write `provider.tf` or `backend.tf`** — they are generated by `root.hcl`. Editing them has no effect (`if_exists = "overwrite_terragrunt"`).
- When adding a module, create both the blueprint (`_envcommon/.../<m>.hcl` → `terraform.source`) and the leaf `terragrunt.hcl` in each env; don't inline module logic into a live dir.
- `fmt` must pass across `infrastructure-modules`, `infrastructure-live`, `infrastructure-bootstrap`, **and** `policies` — a stray unformatted `.tf`/`.hcl` in any of the four fails Gate 1.
- Rego policies target Rego v1 (`import rego.v1`) and package `main`.
- Cost knobs (spot/scaling) live in `env.hcl`; keep dev cheap (spot, min sizes) — the README's FinOps numbers depend on it.
