# CLAUDE.md

This repository maintains a consolidated, framework-agnostic AI agent specification and platform engineering guide in:

👉 **[`.agents/AGENTS.md`](.agents/AGENTS.md)**

Please refer to [`.agents/AGENTS.md`](.agents/AGENTS.md) for:
- Repository layout and the Terragrunt inheritance chain architecture
- Essential local and CI commands (smoke test, format, lint, plan)
- Governance gates (OPA/Conftest, Checkov, Trivy, Infracost)
- CI/CD workflows and zero-key OIDC authentication
- Conventions and gotchas (`root.hcl` generated files, tag propagation)
- Agent Registry definitions and usage (IaC Architect, Policy Auditor, Pipeline Healer, and IaC Generation Agent)
