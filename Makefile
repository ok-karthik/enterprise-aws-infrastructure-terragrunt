# Enterprise AWS Platform — task runner
# Wraps the platform's command surface. Run `make help` for the list.

FMT_DIRS := infrastructure-modules infrastructure-live infrastructure-bootstrap policies
ENV ?= dev

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install the pre-commit hook
	pre-commit install

.PHONY: fmt
fmt: ## Format all HCL/Terraform
	terraform fmt -recursive $(FMT_DIRS)
	terragrunt hcl fmt

.PHONY: fmt-check
fmt-check: ## Check formatting (CI gate)
	terraform fmt -check -recursive $(FMT_DIRS)

.PHONY: lint
lint: ## Run TFLint recursively
	tflint --init
	tflint --recursive --format=compact

.PHONY: validate
validate: ## Full local validation suite (compliance, fmt, init/validate, tflint)
	./infrastructure-live/scripts/smoke-test.sh

.PHONY: security
security: ## Trivy security scan of the repo
	trivy config . --severity CRITICAL,HIGH --ignorefile .trivyignore --tf-exclude-downloaded-modules

.PHONY: plan
plan: ## Plan an environment stack: make plan ENV=dev
	cd infrastructure-live/$(ENV) && terragrunt run --all plan --non-interactive

.PHONY: test
test: ## Run OPA policy unit tests
	conftest verify --policy policies/terraform

.PHONY: docs
docs: ## Regenerate per-module terraform-docs READMEs
	terraform-docs markdown table --output-file README.md --output-mode inject infrastructure-modules/network/vpc
	terraform-docs markdown table --output-file README.md --output-mode inject infrastructure-modules/compute/eks
