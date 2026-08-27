# PLAN.md — IaC Generation Agent: Roadmap & Future Vision

Tracking doc for work beyond the initial ask (a local agent that scaffolds/validates Terragrunt
modules from natural language). Kept at repo root so progress survives context resets — check the
"Execution Log" at the bottom for the current state before resuming.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

## What exists today (baseline, already merged on `agent/iac-generation-mcp`)

- `.agents/scripts/iac_agent.py` — classify → scaffold → fetch-docs → diff → validate/retry loop.
- `.agents/prompts/iac_agent.md` — diff-only generation system prompt.
- `.agents/mcp/docker-compose.yml` — optional `terraform-mcp-server` / `terragrunt-mcp-server` for doc retrieval.
- Verified offline (no AWS creds): `terraform fmt`, `terragrunt hcl fmt`, `terragrunt validate`
  (via `-backend=false` init), `tflint` all pass clean on a real scaffolded module.
- Commits locally to a new branch only — never pushes, never runs `terragrunt apply`.

## Vision

Turn `iac_agent.py` from "generates one module correctly" into a closed-loop platform capability:
requests get generated *and* independently sanity-checked before a human ever sees them; drift gets
proposed as a fix, not just an alert; the whole thing runs as cheaply (cheap model, optionally fully
local) and safely (layered policy-as-code + semantic review, never touching AWS unsupervised) as
possible. Every phase below builds on tooling that already exists in this repo rather than bolting
on new infrastructure.

### Platform Engineering lens

DevOps asked every team to own their own pipeline; Platform Engineering's bet is that most of that
ownership is undifferentiated toil, and a platform team's job is to absorb it behind a self-service,
paved-road interface — an *Internal Developer Platform* — while app teams stay accountable for what
runs, not for hand-rolling how it's provisioned. Concretely, that reframes what this agent is for:

- **It's a paved road, not a code generator.** The value isn't "an LLM writes HCL" — it's that a
  developer who has never read the "Terragrunt inheritance chain" section of `CLAUDE.md` can still
  get a change that's tagged, encrypted, policy-compliant, and correctly wired into the
  `root → envcommon → leaf` chain on the first try. That's the platform absorbing cognitive load
  that today sits on every app team.
- **Curated templates beat free-form generation, the same way a service catalog beats a wiki page.**
  A Backstage-style Internal Developer Platform succeeds by offering a small, opinionated set of
  golden-path templates rather than infinite flexibility. `iac_agent.py` should converge the same
  way: fewer things generated from a blank skeleton, more things picked from a vetted catalog and
  parameterized (see Phase D) — better for developers *and* dramatically more reliable for a cheap
  model, since "fill in these five fields" is a much narrower task than "invent correct HCL."
- **Fast local feedback is the platform's SLA.** The validation ladder (`fmt` → `validate` →
  `tflint` → OPA/Checkov/Trivy) mirrors CI exactly, so "passes locally" is a real promise, not a
  guess — this is the same shift-left contract a platform team makes when it says "if the golden
  path's local checks pass, CI won't surprise you."
- **This *is* the SRE toil-reduction pattern.** Drift-to-diff (B1) and the semantic auditor gate
  (A2) aren't separate features from an SRE lens — they're "eliminate toil" (don't just alert on
  drift, propose the fix) and "defense in depth for change risk" (structural + semantic review
  before anything reaches a human, let alone `apply`) applied to IaC specifically.
- **Self-service needs governance, not just automation.** The reason this agent commits to a branch
  and stops — never pushes, never applies, always re-clears the existing OPA/Checkov/Trivy gates —
  is the platform-engineering answer to "how do you let people self-serve without a platform
  engineer reviewing every PR by hand": governed autonomy, where the guardrails are structural
  (policy-as-code) rather than a human being the bottleneck.

---

## Phase A — Reliability & safety hardening
*No AWS credentials required for any of these — do first.*

- [x] **A1. Policy pre-flight digest.** Auto-extract a human-readable rule summary from
  `policies/terraform/*.rego` and the `.checkov.yaml` `skip-check` list, inject it into
  `iac_agent.md`'s system prompt at runtime. Today the model only learns about a tag/policy
  violation after a failed `conftest`/`checkov` run several steps into the ladder; giving it the
  rules up front cuts retry loops, which matters most for cheap/fast models with a limited retry
  budget.
- [x] **A2. Semantic second-opinion gate.** Wire the existing (but currently unused-by-code)
  `.agents/prompts/auditor.md` "Policy Auditor" persona as an independent LLM call between diff
  generation and `git apply`. Structural tools (`terraform validate`, OPA, Checkov) can't catch
  *semantically* wrong values — overly broad IAM `Resource: "*"`, a public CIDR on the wrong port,
  a value that's syntactically fine but operationally dangerous. A second model call with a
  different framing (auditor, not author) reviewing the diff before it's applied is the standard
  2026 pattern for this gap: generate → structural validate → independent semantic review → apply.
- [x] **A3. Local model provider (Ollama).** Add `--provider ollama` (`http://localhost:11434/v1`,
  OpenAI-compatible) so the entire loop can run with zero API cost and zero network dependency
  beyond doc fetch — the literal "runs on local" from the original ask, not just "runs on my
  laptop but calls a cloud API."
- [x] **A4. Eval harness.** A small fixed set of `(request → expected module_path/task_type)`
  fixtures runnable via `--dry-run`, so swapping models (e.g. benchmarking Gemini Flash vs. Groq
  vs. a local model) or editing prompts has a fast regression check instead of "seems fine."

## Phase B — Close the loop with automation that already exists in this repo

- [x] **B1. Drift-to-diff.** `drift-detection.yml` already opens/comments/closes a GitHub Issue per
  environment on nightly drift. Added `--reconcile` mode to `iac_agent.py` that takes a
  `terraform plan` diff, and instead of just alerting, proposes a corrective HCL diff as a PR
  linked from the drift issue — human still approves, but starts from a fix instead of a raw plan
  dump.
- [x] **B2. ChatOps trigger.** A GitHub Action (`.github/workflows/chatops_generator.yml`) listening
  for an issue/PR comment (`/generate <request>`, `/reconcile <request>`), invoking `iac_agent.py`
  in the toolchain container and pushing the resulting branch as a PR.
- [x] **B3. Cost-aware generation.** Integrated `infracost breakdown` on the generated plan in
  `validation_ladder()` before commit; if projected monthly delta exceeds `--cost-threshold`,
  fails validation and feeds back detailed cost breakdown into the retry prompt to nudge toward
  cheaper resource tiers.

## Phase C — Retrieval depth & scale

- [x] **C1. Real MCP client.** Implemented `.agents/scripts/mcp_client.py` connecting via JSON-RPC
  to `terraform-mcp` (`http://localhost:8080/mcp`) with transparent fallback to GitHub raw scraper
  when offline.
- [x] **C2. Multi-module graph mode.** Added `--graph` decomposition mode (`decompose_request()`)
  breaking multi-component requests (e.g. VPC + EKS + RDS) into an ordered topological sequence of
  single-module generations with inter-module `dependency` blocks and mock outputs.

## Phase D — Platform Engineering integration: golden paths & self-service

- [x] **D1. Golden-path module catalog.** Curated catalog (`.agents/catalog/golden-paths.yaml`) with
  pre-vetted templates (`data-s3-encrypted`, `data-rds-postgres`) that render known-compliant HCL
  deterministically with zero LLM calls.
- [x] **D2. Developer-portal / Backstage integration.** Backstage Software Templates
  (`.agents/backstage/templates/s3-bucket.yaml`, `rds-postgres.yaml`), catalog component registration
  (`catalog-info.yaml`), and runner bridge (`.agents/backstage/runner.py`) returning structured JSON.
- [x] **D3. Stable platform API surface.** Structured `GenerationRequest` and `GenerationResult`
  dataclasses, object-oriented `IaCPlatformAgent` API, and local HTTP REST server (`--serve`).
- [x] **D4. Golden-path health metrics.** Append-only telemetry log (`.agents/metrics/runs.jsonl`)
  and reporting CLI (`.agents/scripts/iac_agent_metrics.py`, `--metrics-summary`).
- [x] **D5. Error-budget-aware gating (SRE lens).** Configured `.agents/sre/error_budgets.yaml` and
  `check_sre_error_budget()` blocking unapproved changes to prod when remaining error budget is
  below critical threshold (10%), with `--bypass-error-budget` override.

## Non-goals / guardrails (carried forward from Phase 0, apply to every phase above)

- Never auto-push, never run `terraform apply`/`terragrunt apply`, never bypass the prod manual-approval gate.
- Every agent-authored change still has to clear the existing OPA/Checkov/Trivy/Infracost gates unchanged — the agent is a PR author, not a bypass.
- Diff-only, single-module-scoped generation stays the default even as Phase C adds a multi-module mode on top.

---

## Execution log

- **2026-08-25** — Phase 0 (MCP compose, orchestrator, prompt, static validation) merged onto
  `agent/iac-generation-mcp`, commit blocked locally only by the repo's pre-commit hook needing
  AWS creds (see prior session) — work is staged/tracked, not lost.
- **2026-08-25 (cont.)** — Researched 2026 practice for semantic IaC review and drift remediation
  to ground Phase A2/B1 (layered policy-as-code + independent semantic check; drift→PR pattern).
  Added the Platform Engineering framing to Vision + Phase D at the user's request.
- **2026-08-25 (cont.)** — Phase A (A1–A4) and Phase D1 all landed and verified tonight.
- **2026-08-27** — Full completion of all remaining Roadmap phases (Phase B, Phase C, and Phase D):
  - **B1 (Drift-to-diff)**: Added `--reconcile <plan_file_or_diff>` to `iac_agent.py` and updated
    `.github/workflows/drift-detection.yml` to capture detailed plan outputs and prompt for ChatOps
    remediation.
  - **B2 (ChatOps trigger)**: Implemented `.github/workflows/chatops_generator.yml` responding to
    `/generate` and `/reconcile` issue comments, running the agent in the platform toolchain container,
    pushing branches, and creating PRs.
  - **B3 (Cost-aware generation)**: Added `--cost-threshold` and Infracost plan breakdown verification
    in `validation_ladder()`, feeding cost overages back into the retry loop.
  - **C1 (Real MCP client)**: Built `.agents/scripts/mcp_client.py` connecting via JSON-RPC 2.0 to
    `terraform-mcp`, with seamless fallback to GitHub raw scraper.
  - **C2 (Multi-module graph mode)**: Implemented `--graph` mode with `decompose_request()` for
    topological sequencing and cross-module dependency injection.
  - **D1+ & D2 (Backstage IDP & Catalog expansion)**: Added `data-rds-postgres` template in
    `.agents/catalog/templates/data-rds-postgres/envcommon.hcl.tmpl`, Backstage Scaffolder templates
    in `.agents/backstage/templates/`, `catalog-info.yaml`, and `runner.py`.
  - **D3 (Platform API & Server)**: Typed dataclasses `GenerationRequest` and `GenerationResult`,
    `IaCPlatformAgent` class, and local HTTP REST server mode (`--serve`).
  - **D4 (Health metrics)**: Append-only JSONL telemetry in `.agents/metrics/runs.jsonl` and
    reporting dashboard `.agents/scripts/iac_agent_metrics.py`.
  - **D5 (SRE error-budget gating)**: Added `.agents/sre/error_budgets.yaml` and prod gating in
    `check_sre_error_budget()`.
  - **Verification**: Created `.agents/tests/test_platform.py` (7 tests, all passing), verified
    `iac_agent_eval.py` (100% passing), tested dry-runs, and confirmed `terraform fmt` /
    `terragrunt hcl fmt` remain clean.
