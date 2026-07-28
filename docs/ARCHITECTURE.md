# Architecture

This platform follows a **Hierarchical Blueprint Pattern**: a generic, reusable Terraform library is kept strictly separate from live, per-environment configuration, so nothing is duplicated across environments.

## The two halves

- **`infrastructure-modules/`** — generic, reusable Terraform (`network/vpc`, `compute/eks`). Pure `.tf`, no environment specifics. Security hardening lives here, not just in CI.
- **`infrastructure-live/`** — Terragrunt configuration that composes those modules per environment and region.

## The inheritance chain

To understand any live module you read it top-down through these layers — a leaf `terragrunt.hcl` is often ~10 lines because it inherits everything else:

1. **`infrastructure-live/root.hcl`** — included by every leaf. Generates `provider.tf` and `backend.tf` at runtime and injects `default_tags` (`Environment`, `Service`, `Project`, `ManagedBy`, `Account`). The S3 backend bucket name and tags are computed here — modules never hand-write provider/backend blocks.
2. **`_envcommon/<category>/<module>.hcl`** — the shared blueprint per module type. Sets `terraform.source` (into `infrastructure-modules/`), declares `dependency` blocks with `mock_outputs` for plan-time, and default `inputs`. Cross-module wiring (EKS → VPC subnets) lives here.
3. **Data files** loaded via `find_in_parent_folders`:
   - `<env>/account.hcl` — account id, alias
   - `<env>/env.hcl` — `env`, `cluster_name`, cost knobs (`min_size`, `desired_size`, `enable_nat_gateway`)
   - `<env>/<region>/region.hcl` — `aws_region`
4. **Leaf** `<env>/<region>/<category>/<module>/terragrunt.hcl` — includes `root` + the matching `_envcommon` file and only overrides env-specific values (e.g. dev shrinks EKS node counts; prod runs `desired_size = 0`).

`path_relative_to_include()` drives naming everywhere — state key, the `Service` tag, env detection — so **directory layout is a contract, not a convention**. Allowed envs are `dev`/`prod`/`staging`; regions must be `eu-*`/`us-*` (enforced by `infrastructure-live/scripts/smoke-test.sh`).

## Bootstrap (day-0)

`infrastructure-bootstrap/` is a separate stack that must exist before `infrastructure-live` can deploy. It provisions the GitHub OIDC identity provider, CI IAM roles, the S3 state bucket, and the DynamoDB lock table — i.e. the very backend the live stacks depend on.

## State backend

Configured centrally in `root.hcl`: S3 bucket per account/region with versioning (point-in-time rollback), DynamoDB locking (prevents concurrent-apply corruption), block-public-access, and AES-256 SSE at rest.
