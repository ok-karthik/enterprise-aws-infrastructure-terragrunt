# CI/CD, Governance & Self-Healing

All jobs run inside a purpose-built toolchain container (`ghcr.io/ok-karthik/infrastructure-toolchain`, defined in `.github/docker/Dockerfile`) so local and CI tool versions never drift.

## Pipeline (`terragrunt.yml` + `reusable-terragrunt.yml`)

1. **Static analysis** (parallel with planning): `terraform fmt -check`, `terraform validate`, TFLint, Checkov (HCL), Trivy. Results upload as SARIF to the GitHub Security tab.
2. **Plan** per environment: `terragrunt run --all plan` produces `tfplan.bin`, converted to `tfplan.json` and uploaded as an artifact.
3. **Governance gates** consume the plan JSON:
   - **OPA/Conftest** against `policies/terraform/` — mandatory tagging, no legacy instance families.
   - **Checkov** (plan-level, CIS benchmark) and **Trivy** (CRITICAL/HIGH) as blocking gates.
4. **Cost** — Infracost posts a per-module breakdown as a PR comment (`tf-summarize` adds a change summary).
5. **Apply** — on push to `main`, `apply-dev` runs, then `apply-prod`, which is gated by a protected GitHub **Environment** requiring manual approval.

A change can pass `terraform validate` and still fail the governance gates — the gates run against the *planned* resources, not just the HCL.

## Authentication — zero-key OIDC

Jobs assume short-lived IAM roles (`vars.AWS_DEV_ROLE_ARN` / `vars.AWS_PROD_ROLE_ARN`) via GitHub Actions OIDC through the `setup-platform` composite action. No static AWS credentials exist in the repo or CI.

## Governance rules (`policies/terraform/`)

- `require_service_tag.rego` — every created/updated resource must carry `Service`, `Environment`, `Project` (checked in `tags_all`; normally satisfied by `root.hcl` default tags).
- `no_legacy_instances.rego` — blocks `t2.`, `m3.`, `m4.`, `c3.`, `c4.` families.

Both are Rego v1 (`import rego.v1`, `package main`) and are unit-tested with `conftest verify` (see `*_test.rego`).

## Nightly drift detection (`drift-detection.yml`)

A matrix job over dev/prod compares live AWS against state each night and self-manages **one GitHub Issue per environment**: creates on new drift, comments while it persists, and auto-closes when resolved. Each env uses its own IAM role for isolation.

## Self-healing CI (`pipeline_healer.yml` + `.agents/`)

Triggered on a failed "Terragrunt CI/CD" run:

1. Downloads logs for the failed jobs only (GitHub Jobs API) to fit LLM token limits.
2. If it detects a provider-lock mismatch, runs `init -upgrade -backend=false` across all active `.terraform.lock.hcl` files (temporarily mocking `get_aws_account_id()` so parsing works without AWS creds) and commits the result.
3. Otherwise sends logs + repo tree to a Groq-hosted LLM, extracts a `git diff`, applies it, and pushes a remediation commit to the PR branch.

## Dependency automation

Renovate (`renovate.json`) tracks Terraform Registry modules (`tfr://`), toolchain binary versions in the Dockerfile ARGs, and GitHub Actions — grouping non-major bumps into a single PR and isolating majors for review.
