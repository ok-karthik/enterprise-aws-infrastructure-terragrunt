#!/usr/bin/env python3
"""
IaC Generation Agent — Autonomous Platform Engineering & SRE Agent
Scaffolds, validates, reconciles, and governs Terragrunt/Terraform modules
from natural language, golden-path catalogs, or drift plan outputs.

Features:
- Deterministic Golden-Path Catalog (Phase D1, D1+)
- Policy Pre-flight Digest & Semantic Second-Opinion Gate (Phases A1, A2)
- Multi-provider support: Gemini, Groq, OpenAI, and fully-offline local Ollama (Phase A3)
- Real MCP Client with fallback scraper (Phase C1)
- Multi-Module Graph Decomposition (Phase C2)
- Drift-to-Diff Plan Reconciliation (Phase B1)
- Cost-Aware Generation with Infracost feedback (Phase B3)
- Platform API Surface & Local HTTP Server (Phase D3)
- Append-only Health Telemetry (Phase D4)
- SRE Error-Budget Guardrails (Phase D5)
"""

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional
import urllib.error
import urllib.request

# Local imports
BASE_DIR = Path(__file__).resolve().parent.parent  # .agents/
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
PROMPT_PATH = BASE_DIR / "prompts" / "iac_agent.md"
AUDITOR_PROMPT_PATH = BASE_DIR / "prompts" / "auditor.md"
GENERATE_MODULE_SCRIPT = REPO_ROOT / "infrastructure-live" / "scripts" / "generate-module.sh"
CATALOG_PATH = BASE_DIR / "catalog" / "golden-paths.yaml"
CATALOG_TEMPLATES_DIR = BASE_DIR / "catalog" / "templates"
METRICS_PATH = BASE_DIR / "metrics" / "runs.jsonl"
SRE_CONFIG_PATH = BASE_DIR / "sre" / "error_budgets.yaml"

VALID_ENVS = {"dev", "staging", "prod"}


# ==========================================
# Typed Platform API Dataclasses (Phase D3)
# ==========================================
@dataclass
class GenerationRequest:
    request: str
    env: str = "dev"
    region: str = "eu-central-1"
    provider: str = "gemini"
    model: Optional[str] = None
    max_retries: int = 3
    skip_plan: bool = False
    no_branch: bool = False
    dry_run: bool = False
    cost_threshold: Optional[float] = None
    reconcile_plan: Optional[str] = None
    graph_mode: bool = False
    bypass_error_budget: bool = False
    module_path: Optional[str] = None
    dependencies: Optional[list[str]] = None


@dataclass
class GenerationResult:
    success: bool
    branch: Optional[str] = None
    files_changed: list[str] = field(default_factory=list)
    catalog_id: Optional[str] = None
    task_type: str = "new_module"
    module_path: Optional[str] = None
    attempts: int = 0
    failed_steps: list[str] = field(default_factory=list)
    cost_monthly_delta: Optional[float] = None
    audit_verdict: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


# ==========================================
# 1. LLM client setup (provider-agnostic)
# ==========================================
def get_client(provider: str):
    from openai import OpenAI

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            sys.exit("❌ GEMINI_API_KEY is not set.")
        return (
            OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=api_key),
            "gemini-flash-latest",
        )
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            sys.exit("❌ GROQ_API_KEY is not set.")
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key), "llama-3.3-70b-versatile"
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            sys.exit("❌ OPENAI_API_KEY is not set.")
        return OpenAI(api_key=api_key), "gpt-4o-mini"
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OpenAI(base_url=base_url, api_key="ollama"), os.getenv("OLLAMA_MODEL", "llama3.1")
    sys.exit(f"❌ Unknown provider: {provider}")


def run(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 900) -> subprocess.CompletedProcess:
    print(f"   $ {' '.join(cmd)}" + (f"   (cwd={cwd})" if cwd else ""))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)


# ==========================================
# 2. Golden-Path Catalog & Classification
# ==========================================
def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    import yaml

    return yaml.safe_load(CATALOG_PATH.read_text()) or []


def match_catalog(request: str, catalog: list[dict]) -> Optional[dict]:
    req_lower = request.lower()
    best, best_score = None, 0
    for entry in catalog:
        score = sum(1 for kw in entry.get("keywords", []) if kw.lower() in req_lower)
        if score > best_score:
            best, best_score = entry, score
    return best


def classify_request(client, model: str, request: str, default_env: str, default_region: str) -> dict:
    system = (
        "You classify infrastructure change requests for a Terragrunt monorepo. "
        "Respond with ONLY a JSON object, no markdown fences, no prose, matching exactly this schema:\n"
        '{"task_type": "new_module|modify_module|modify_scaling|add_policy|other", '
        '"module_path": "<category>/<name>", "env": "dev|staging|prod", "region": "<aws region>", '
        '"resource_hint": "<primary terraform resource type, e.g. aws_s3_bucket, or empty string>"}\n'
        "module_path must be lowercase, hyphenated, in the form 'category/name' (e.g. 'storage/build-artifacts')."
    )
    user = f"Request: {request}\nDefault env if unspecified: {default_env}\nDefault region if unspecified: {default_region}"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    data = json.loads(raw)

    if not re.match(r"^[a-z0-9-]+/[a-z0-9-]+$", data.get("module_path", "")):
        sys.exit(f"❌ Model returned an invalid module_path: {data.get('module_path')!r}")
    if data.get("env") not in VALID_ENVS:
        data["env"] = default_env
    if not data.get("region"):
        data["region"] = default_region
    return data


# ==========================================
# 2b. Multi-Module Graph Decomposition (Phase C2)
# ==========================================
def decompose_request(client, model: Optional[str], request: str, env: str, region: str) -> list[dict]:
    """
    Decomposes composite requests (e.g. 'VPC + EKS + RDS') into an ordered list
    of module definitions respecting dependency ordering.
    """
    if client is None or not model:
        # Fallback heuristic for offline / dry-run
        parts = []
        req_lower = request.lower()
        if "vpc" in req_lower or "network" in req_lower:
            parts.append({"module_path": "network/vpc", "request": "create VPC network module", "dependencies": []})
        if "eks" in req_lower or "kubernetes" in req_lower:
            parts.append({"module_path": "compute/eks", "request": "provision EKS cluster", "dependencies": ["network/vpc"]})
        if "rds" in req_lower or "postgres" in req_lower or "database" in req_lower:
            parts.append({"module_path": "data/rds-postgres", "request": "create RDS PostgreSQL database", "dependencies": ["network/vpc"]})
        if "s3" in req_lower or "bucket" in req_lower:
            parts.append({"module_path": "data/s3-encrypted", "request": "create S3 bucket", "dependencies": []})
        return parts or [{"module_path": "storage/app", "request": request, "dependencies": []}]

    system = (
        "You decompose complex multi-module cloud infrastructure requests for Terragrunt. "
        "Return ONLY a JSON array of objects in topological dependency order (prerequisites first). "
        "Schema:\n"
        '[{"module_path": "<category>/<name>", "request": "<sub-request>", "dependencies": ["<parent_module_path>"]}]\n'
        "Valid categories: network, compute, data, security, storage. No markdown fences."
    )
    user = f"Request: {request}\nEnv: {env}\nRegion: {region}"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list) and data:
            return data
    except Exception as e:
        print(f"⚠️ Graph decomposition parse error: {e}")
    return [{"module_path": "storage/app", "request": request, "dependencies": []}]


# ==========================================
# 3. Scaffolding & Template Rendering
# ==========================================
_SLUG_STOPWORDS = {"a", "an", "the", "add", "for", "module", "please", "create", "new", "to", "of", "with", "in", "on"}


def _slugify(text: str, max_len: int = 30) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _SLUG_STOPWORDS]
    slug = "-".join(words) or re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug.strip("-") or "resource"


def scaffold_from_template(entry: dict, module_path: str, env: str, region: str, request: str) -> list[Path]:
    template_dir = CATALOG_TEMPLATES_DIR / entry["template"]

    res = run(["bash", str(GENERATE_MODULE_SCRIPT), module_path, env, region])
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr.strip())
    leaf_file = REPO_ROOT / "infrastructure-live" / env / region / module_path / "terragrunt.hcl"

    envcommon_path = REPO_ROOT / "infrastructure-live" / "_envcommon" / f"{module_path}.hcl"
    envcommon_path.parent.mkdir(parents=True, exist_ok=True)
    slug = _slugify(request)
    rendered = (
        (template_dir / "envcommon.hcl.tmpl")
        .read_text()
        .replace("__BUCKET_SLUG__", slug)
        .replace("__DB_SLUG__", slug)
        .replace("__DB_NAME__", slug.replace("-", "_")[:30])
        .replace("__TABLE_SLUG__", slug)
        .replace("__SERVICE_NAME__", module_path.split("/")[-1])
    )
    envcommon_path.write_text(rendered)

    created = []
    if leaf_file.exists():
        created.append(leaf_file)
    created.append(envcommon_path)
    return created


def scaffold_skeleton(module_path: str, env: str, region: str, dependencies: Optional[list[str]] = None) -> list[Path]:
    created = []
    res = run(["bash", str(GENERATE_MODULE_SCRIPT), module_path, env, region])
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr.strip())

    leaf_dir = REPO_ROOT / "infrastructure-live" / env / region / module_path
    leaf_file = leaf_dir / "terragrunt.hcl"
    if leaf_file.exists():
        created.append(leaf_file)

    envcommon_path = REPO_ROOT / "infrastructure-live" / "_envcommon" / f"{module_path}.hcl"
    if not envcommon_path.exists():
        envcommon_path.parent.mkdir(parents=True, exist_ok=True)
        dep_blocks = ""
        if dependencies:
            for dep in dependencies:
                dep_name = dep.split("/")[-1]
                dep_blocks += (
                    f'dependency "{dep_name}" {{\n'
                    f'  config_path = "${{get_terragrunt_dir()}}/../../{dep}"\n'
                    f"  mock_outputs = {{\n"
                    f'    id = "{dep_name}-mock-id"\n'
                    f"  }}\n"
                    f'  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "show"]\n'
                    f"}}\n\n"
                )

        envcommon_path.write_text(
            f"# Common configuration for {module_path} modules across all environments.\n\n"
            f"terraform {{\n"
            f'  source = "${{get_repo_root()}}/infrastructure-modules/{module_path}"\n'
            f"}}\n\n"
            f"locals {{\n"
            f'  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))\n'
            f"  env      = local.env_vars.locals.env\n"
            f"}}\n\n"
            f"{dep_blocks}"
            f"inputs = {{}}\n"
        )
        created.append(envcommon_path)
    else:
        created.append(envcommon_path)

    module_dir = REPO_ROOT / "infrastructure-modules" / module_path
    main_tf_header = (
        "# Primary resources for this module.\n\n"
        "terraform {\n"
        '  required_version = ">= 1.5.0"\n'
        "  required_providers {\n"
        "    aws = {\n"
        '      source  = "hashicorp/aws"\n'
        '      version = ">= 5.0"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    for fname, header in (
        ("main.tf", main_tf_header),
        ("variables.tf", "# Input variables for this module."),
        ("outputs.tf", "# Outputs exposed by this module."),
    ):
        fpath = module_dir / fname
        if not fpath.exists():
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(f"{header}\n" if fname != "main.tf" else header)
        created.append(fpath)

    return created


# ==========================================
# 4. Doc Retrieval: MCP Client + GitHub Fallback (Phase C1)
# ==========================================
def fetch_docs(resource_hint: str) -> str:
    """Queries MCP server first; falls back to GitHub raw docs scraper."""
    if not resource_hint or not resource_hint.startswith("aws_"):
        return ""

    # 1. Try MCP client
    try:
        from mcp_client import MCPClient

        client = MCPClient()
        mcp_doc = client.get_provider_doc(resource_hint)
        if mcp_doc:
            print(f"   📡 Fetched provider docs from MCP server for {resource_hint}")
            return mcp_doc[:8000]
    except Exception:
        pass

    # 2. Fallback: GitHub raw scraper
    slug = resource_hint[len("aws_") :]
    url = f"https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/main/website/docs/r/{slug}.html.markdown"
    try:
        req_obj = urllib.request.Request(url, headers={"User-Agent": "IaC-Platform-Agent"})
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            if resp.status == 200:
                print(f"   🌐 Fetched provider docs from GitHub raw fallback for {resource_hint}")
                return resp.read().decode("utf-8", errors="replace")[:8000]
    except Exception as e:
        print(f"⚠️ Doc fetch fallback failed for {resource_hint}: {e}")
    return ""


# Legacy alias
fetch_aws_doc = fetch_docs


# ==========================================
# 4b. Policy Digest & Semantic Audit (Phases A1, A2)
# ==========================================
def build_policy_digest() -> str:
    lines = ["## Active governance rules (auto-extracted — treat as binding constraints, not suggestions)"]
    rego_dir = REPO_ROOT / "policies" / "terraform"
    for rego_file in sorted(rego_dir.glob("*.rego")) if rego_dir.exists() else []:
        if rego_file.name.endswith("_test.rego"):
            continue
        content = rego_file.read_text()
        messages = re.findall(r'sprintf\(\s*"([^"]+)"', content)
        list_literals = re.findall(r"(\w+)\s*:=\s*(\[[^\]]*\])", content)
        if not (messages or list_literals):
            continue
        lines.append(f"\n### {rego_file.name}")
        for name, literal in list_literals:
            lines.append(f"- {name} = {literal}")
        for msg in messages:
            lines.append(f"- Rule: {msg}")

    checkov_path = REPO_ROOT / ".checkov.yaml"
    if checkov_path.exists():
        skip_lines = re.findall(r"^\s*-\s*(CKV\S*)\s*#\s*(.+)$", checkov_path.read_text(), re.MULTILINE)
        if skip_lines:
            lines.append("\n### .checkov.yaml — pre-approved suppressions:")
            for check_id, reason in skip_lines:
                lines.append(f"- {check_id}: {reason.strip()}")

    return "\n".join(lines)


def semantic_audit(client, model: str, files: list[Path]) -> tuple[bool, str]:
    if not AUDITOR_PROMPT_PATH.exists() or client is None:
        return True, "PASSED"
    system = AUDITOR_PROMPT_PATH.read_text()
    file_blob = "\n\n".join(f"=== {p.relative_to(REPO_ROOT)} ===\n{p.read_text()}" for p in files if p.exists())
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": file_blob}],
        temperature=0.0,
    )
    verdict = resp.choices[0].message.content.strip()
    if re.search(r"STATUS:\s*PASSED", verdict, re.IGNORECASE):
        return True, verdict
    return False, verdict


# ==========================================
# 4c. SRE Error-Budget Guardrail (Phase D5)
# ==========================================
def is_in_change_window(now_utc: datetime, windows: list[str]) -> bool:
    """Checks if a UTC timestamp falls within any of the specified change windows.
    Format example: 'Mon-Thu 08:00-16:00 UTC' or 'Mon-Fri 09:00-17:00 UTC'.
    """
    day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    weekday = now_utc.weekday()
    cur_time = now_utc.time()

    for win in windows:
        m = re.match(r"([A-Za-z]{3})-([A-Za-z]{3})\s+(\d{2}:\d{2})-(\d{2}:\d{2})\s+UTC", win.strip())
        if not m:
            continue
        start_day, end_day, start_time_str, end_time_str = m.groups()
        start_day_idx = day_map.get(start_day)
        end_day_idx = day_map.get(end_day)
        if start_day_idx is None or end_day_idx is None:
            continue

        t_start = datetime.strptime(start_time_str, "%H:%M").time()
        t_end = datetime.strptime(end_time_str, "%H:%M").time()

        if start_day_idx <= end_day_idx:
            day_matches = start_day_idx <= weekday <= end_day_idx
        else:
            day_matches = weekday >= start_day_idx or weekday <= end_day_idx

        if day_matches and t_start <= cur_time <= t_end:
            return True

    return False


def check_sre_error_budget(env: str, bypass: bool = False, now: Optional[datetime] = None) -> tuple[bool, str]:
    """Inspects SRE error budgets and change windows for production change-risk gating."""
    if env != "prod" or bypass:
        return True, "Non-prod environment or SRE budget bypass active."

    import yaml

    if not SRE_CONFIG_PATH.exists():
        return True, "No error_budgets.yaml found."

    config = yaml.safe_load(SRE_CONFIG_PATH.read_text()) or {}
    prod_cfg = config.get("environments", {}).get("prod", {})
    remaining = float(os.getenv("SLO_ERROR_BUDGET_REMAINING", prod_cfg.get("error_budget_remaining_pct", 100.0)))
    critical_threshold = float(prod_cfg.get("critical_threshold_pct", 10.0))

    if remaining < critical_threshold and prod_cfg.get("freeze_on_exhaustion", True):
        return (
            False,
            f"❌ SRE Error Budget Exhausted: prod remaining error budget is {remaining:.1f}%, "
            f"below critical threshold of {critical_threshold:.1f}%. Prod changes are frozen. "
            f"Provide --bypass-error-budget with explicit SRE VP sign-off to proceed.",
        )

    # Change window verification
    allowed_windows = prod_cfg.get("allowed_change_windows", [])
    enforce_windows = prod_cfg.get("enforce_change_windows", False) or os.getenv("ENFORCE_CHANGE_WINDOWS") == "1"
    if allowed_windows:
        now_utc = now or datetime.now(timezone.utc)
        in_window = is_in_change_window(now_utc, allowed_windows)
        if not in_window:
            msg = (
                f"SRE Change Window Restriction: current time ({now_utc.strftime('%a %H:%M UTC')}) "
                f"is outside allowed production change windows ({', '.join(allowed_windows)})."
            )
            if enforce_windows:
                return False, f"❌ {msg} Prod changes are frozen outside change windows."
            print(f"⚠️  {msg} (enforce_change_windows is disabled, proceeding)")

    return True, f"Prod error budget healthy: {remaining:.1f}% remaining."


# ==========================================
# 5. Diff Generation & Application
# ==========================================
def extract_diff(text: str) -> Optional[str]:
    match = re.search(r"```(?:diff)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        block = match.group(1)
        if "--- " in block and "+++" in block:
            return block
    if "--- " in text and "+++ " in text:
        return text
    return None


def generate_diff(client, model: str, system_prompt: str, request: str, files: list[Path], doc_context: str, feedback: Optional[str]) -> str:
    file_blob = "\n\n".join(f"=== {p.relative_to(REPO_ROOT)} ===\n{p.read_text()}" for p in files)
    user = f"Task: {request}\n\nCurrent file contents (edit ONLY these files, output unified diff):\n{file_blob}\n\n"
    if doc_context:
        user += f"Relevant provider documentation:\n{doc_context}\n\n"
    if feedback:
        user += f"The previous attempt failed validation. Fix ONLY this error with a minimal diff:\n{feedback}\n\n"

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


def apply_diff(diff_text_raw: str) -> tuple[bool, str]:
    diff_text = extract_diff(diff_text_raw)
    if not diff_text:
        return False, "Could not extract a valid unified diff from the model response."

    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as f:
        f.write(diff_text)
        patch_path = f.name

    check = run(["git", "apply", "--check", patch_path], cwd=REPO_ROOT)
    if check.returncode != 0:
        return False, f"`git apply --check` failed:\n{check.stderr.strip()}"

    applied = run(["git", "apply", patch_path], cwd=REPO_ROOT)
    if applied.returncode != 0:
        return False, f"`git apply` failed:\n{applied.stderr.strip()}"

    return True, "Patch applied."


# ==========================================
# 6. Validation Ladder & Cost Gating (Phase B3)
# ==========================================
def _tail(res: subprocess.CompletedProcess, n: int = 60) -> str:
    return "\n".join((res.stdout + res.stderr).splitlines()[-n:])


@contextmanager
def mock_account_id():
    targets = []
    for path in (REPO_ROOT / "infrastructure-live").rglob("*.hcl"):
        if ".terragrunt-cache" in path.parts:
            continue
        content = path.read_text()
        if "get_aws_account_id()" in content:
            targets.append((path, content))
    for path, content in targets:
        path.write_text(content.replace("get_aws_account_id()", '"123456789012"'))
    try:
        yield
    finally:
        for path, content in targets:
            path.write_text(content)


def _find_terragrunt_cache_dir(leaf_dir: Path) -> Optional[Path]:
    cache_root = leaf_dir / ".terragrunt-cache"
    if not cache_root.exists():
        return None
    candidates = sorted(cache_root.glob("*/*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for c in candidates:
        if c.is_dir() and (c / ".terraform").exists():
            return c
    return None


def offline_validate(leaf_dir: Path) -> subprocess.CompletedProcess:
    init_res = run(["terragrunt", "init", "-upgrade", "-backend=false", "--non-interactive"], cwd=leaf_dir)
    if init_res.returncode != 0:
        return init_res
    cache_dir = _find_terragrunt_cache_dir(leaf_dir)
    if not cache_dir:
        init_res.returncode = 1
        init_res.stderr += "\n(iac_agent) Could not locate .terragrunt-cache working directory after init."
        return init_res
    return run(["terraform", "validate"], cwd=cache_dir)


def validation_ladder(
    module_path: str,
    env: str,
    region: str,
    skip_plan: bool,
    cost_threshold: Optional[float] = None,
) -> tuple[bool, Optional[str], Optional[str], Optional[float]]:
    """
    Validation ladder with syntax, static lint, offline validation, OPA/Checkov/Trivy,
    and Infracost monthly budget enforcement.
    """
    leaf_dir = REPO_ROOT / "infrastructure-live" / env / region / module_path
    module_dir = REPO_ROOT / "infrastructure-modules" / module_path

    fmt_step = (
        "terraform fmt",
        [
            "terraform", "fmt", "-check", "-recursive",
            "infrastructure-modules", "infrastructure-live", "infrastructure-bootstrap", "policies",
        ],
        REPO_ROOT,
    )
    hcl_fmt_step = ("terragrunt hcl fmt", ["terragrunt", "hcl", "fmt", "--check"], REPO_ROOT)

    for name, cmd, cwd in (fmt_step, hcl_fmt_step):
        res = run(cmd, cwd=cwd)
        if res.returncode != 0:
            return False, name, _tail(res), None
        print(f"   ✅ {name} passed")

    print("   $ terragrunt validate (offline)" if skip_plan else "   $ terragrunt validate --non-interactive")
    with mock_account_id():
        res = offline_validate(leaf_dir) if skip_plan else run(["terragrunt", "validate", "--non-interactive"], cwd=leaf_dir)
    if res.returncode != 0:
        return False, "terragrunt validate", _tail(res), None
    print("   ✅ terragrunt validate passed")

    if module_dir.exists():
        res = run(["tflint", "--chdir", str(module_dir), "--format=compact"], cwd=REPO_ROOT)
        if res.returncode != 0:
            return False, "tflint", _tail(res), None
        print("   ✅ tflint passed")
    else:
        print(f"   ⏭️  Skipping tflint — {module_dir.relative_to(REPO_ROOT)} doesn't exist (registry module).")

    if skip_plan:
        print("   ⏭️  Skipping plan/OPA/Checkov/Trivy/Infracost — no AWS credentials available (--skip-plan).")
        return True, None, None, None

    res = run(["terragrunt", "plan", "-out=tfplan.bin", "--non-interactive"], cwd=leaf_dir)
    if res.returncode != 0:
        return False, "terragrunt plan", _tail(res), None
    print("   ✅ terragrunt plan passed")

    show = run(["terraform", "show", "-json", "tfplan.bin"], cwd=leaf_dir)
    if show.returncode != 0:
        return False, "terraform show -json", show.stderr.strip(), None
    plan_json = leaf_dir / "tfplan.json"
    plan_json.write_text(show.stdout)

    # Cost Gating with Infracost (Phase B3)
    monthly_cost = None
    if cost_threshold is not None:
        cost_res = run(["infracost", "breakdown", "--path", str(plan_json), "--format", "json"], cwd=leaf_dir)
        if cost_res.returncode == 0:
            try:
                cost_data = json.loads(cost_res.stdout)
                monthly_cost = float(cost_data.get("totalMonthlyCost", 0.0))
                print(f"   💰 Infracost projected monthly cost: ${monthly_cost:.2f}/mo (limit: ${cost_threshold:.2f}/mo)")
                if monthly_cost > cost_threshold:
                    msg = (
                        f"Projected monthly cost of ${monthly_cost:.2f}/mo exceeds limit of ${cost_threshold:.2f}/mo. "
                        f"Reduce instance sizes, replica count, or disk tiers to fit within the budget."
                    )
                    return False, "infracost cost limit", msg, monthly_cost
                print("   ✅ Infracost cost check passed")
            except Exception as e:
                print(f"   ⚠️ Could not parse Infracost JSON: {e}")
        else:
            print("   ⏭️  Skipping Infracost cost check (infracost CLI or API key unavailable).")

    gates = [("conftest", ["conftest", "test", "--policy", str(REPO_ROOT / "policies" / "terraform"), str(plan_json)], REPO_ROOT)]
    if module_dir.exists():
        gates.append(("checkov", ["checkov", "-d", str(module_dir), "--config-file", str(REPO_ROOT / ".checkov.yaml")], REPO_ROOT))
        gates.append((
            "trivy",
            [
                "trivy", "config", str(module_dir),
                "--severity", "CRITICAL,HIGH",
                "--ignorefile", str(REPO_ROOT / ".trivyignore"),
                "--tf-exclude-downloaded-modules",
            ],
            REPO_ROOT,
        ))

    for name, cmd, cwd in gates:
        res = run(cmd, cwd=cwd)
        if res.returncode != 0:
            return False, name, _tail(res), monthly_cost
        print(f"   ✅ {name} passed")

    return True, None, None, monthly_cost


# ==========================================
# 7. Telemetry & Metrics (Phase D4)
# ==========================================
def record_telemetry(event: dict):
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ==========================================
# 8. Platform Agent Core Orchestrator (Phase D3)
# ==========================================
class IaCPlatformAgent:
    """Unified API for executing IaC generation, reconciliation, and graph workflows."""

    def __init__(self, catalog: Optional[list[dict]] = None):
        self.catalog = catalog if catalog is not None else load_catalog()

    def generate(self, req: GenerationRequest) -> GenerationResult:
        start_time = time.time()
        failed_steps = []

        # 1. SRE Error Budget Check (Phase D5)
        sre_ok, sre_msg = check_sre_error_budget(req.env, req.bypass_error_budget)
        if not sre_ok:
            print(sre_msg)
            return GenerationResult(
                success=False,
                error_message=sre_msg,
                duration_seconds=time.time() - start_time,
            )
        print(f"🛡️  {sre_msg}")

        # 2. Branch setup
        branch_name = None
        if not req.no_branch and not req.dry_run:
            slug = re.sub(r"[^a-z0-9]+", "-", req.request.lower()).strip("-")[:40]
            branch_name = f"agent/iac-{slug}"
            res = run(["git", "checkout", "-b", branch_name], cwd=REPO_ROOT)
            if res.returncode != 0:
                run(["git", "checkout", branch_name], cwd=REPO_ROOT)

        # 3. Client & model
        client, default_model = (None, None) if req.dry_run else get_client(req.provider)
        model = req.model or default_model

        # 4. Catalog matching or classification
        catalog_entry = match_catalog(req.request, self.catalog)
        if req.module_path:
            classification = {
                "task_type": "new_module",
                "module_path": req.module_path,
                "env": req.env,
                "region": req.region,
                "resource_hint": catalog_entry.get("resource_hint", "") if catalog_entry else "",
            }
        elif catalog_entry:
            classification = {
                "task_type": "new_module",
                "module_path": catalog_entry["module_path"],
                "env": req.env,
                "region": req.region,
                "resource_hint": catalog_entry.get("resource_hint", ""),
            }
            print(f"📚 Golden-path match: {catalog_entry['id']}")
        elif req.dry_run:
            classification = {
                "task_type": "new_module",
                "module_path": "storage/example",
                "env": req.env,
                "region": req.region,
                "resource_hint": "",
            }
        else:
            classification = classify_request(client, model, req.request, req.env, req.region)

        module_path = classification["module_path"]
        env = classification["env"]
        region = classification["region"]
        has_template = bool(catalog_entry and catalog_entry.get("template"))

        leaf_file = REPO_ROOT / "infrastructure-live" / env / region / module_path / "terragrunt.hcl"
        envcommon_path = REPO_ROOT / "infrastructure-live" / "_envcommon" / f"{module_path}.hcl"

        if req.dry_run:
            files = [leaf_file, envcommon_path]
            res = GenerationResult(
                success=True,
                branch=branch_name,
                files_changed=[str(f) for f in files],
                catalog_id=catalog_entry["id"] if catalog_entry else None,
                task_type=classification["task_type"],
                module_path=module_path,
                attempts=0,
                duration_seconds=time.time() - start_time,
            )
            record_telemetry({**asdict(res), "timestamp": datetime.now(timezone.utc).isoformat(), "request": req.request})
            return res

        # 5. Scaffolding
        if has_template:
            files = scaffold_from_template(catalog_entry, module_path, env, region, req.request)
        else:
            files = scaffold_skeleton(module_path, env, region, req.dependencies)

        # 6. Generation & Validation Loop
        system_prompt = PROMPT_PATH.read_text() + "\n\n" + build_policy_digest()
        doc_context = fetch_docs(classification.get("resource_hint", ""))
        feedback = None
        final_verdict = None
        monthly_cost = None

        for attempt in range(1, req.max_retries + 1):
            if attempt == 1 and has_template:
                print("📦 Using golden-path template — skipping LLM generation for attempt 1.")
            else:
                diff_text = generate_diff(client, model, system_prompt, req.request, files, doc_context, feedback)
                applied, msg = apply_diff(diff_text)
                if not applied:
                    failed_steps.append("git apply")
                    feedback = msg
                    continue

            # Semantic Audit (Phase A2)
            audited, verdict = semantic_audit(client, model, files)
            final_verdict = verdict
            if not audited:
                failed_steps.append("semantic_audit")
                feedback = f"Independent Policy Audit flagged issue:\n{verdict}\nFix it."
                continue

            # Validation Ladder (Phase B3 Cost Gating included)
            passed, failed_step, tail, monthly_cost = validation_ladder(
                module_path, env, region, req.skip_plan, req.cost_threshold
            )
            if passed:
                # Commit locally
                run(["git", "add", "--", str(REPO_ROOT / "infrastructure-live" / env / region / module_path)], cwd=REPO_ROOT)
                run(["git", "add", "--", str(REPO_ROOT / "infrastructure-live" / "_envcommon" / f"{module_path}.hcl")], cwd=REPO_ROOT)
                if (REPO_ROOT / "infrastructure-modules" / module_path).exists():
                    run(["git", "add", "--", str(REPO_ROOT / "infrastructure-modules" / module_path)], cwd=REPO_ROOT)
                run(["git", "commit", "-m", f"feat(iac-agent): {req.request}"], cwd=REPO_ROOT)

                res = GenerationResult(
                    success=True,
                    branch=branch_name,
                    files_changed=[str(f) for f in files],
                    catalog_id=catalog_entry["id"] if catalog_entry else None,
                    task_type=classification["task_type"],
                    module_path=module_path,
                    attempts=attempt,
                    failed_steps=failed_steps,
                    cost_monthly_delta=monthly_cost,
                    audit_verdict=final_verdict,
                    duration_seconds=time.time() - start_time,
                )
                record_telemetry({**asdict(res), "timestamp": datetime.now(timezone.utc).isoformat(), "request": req.request})
                return res

            failed_steps.append(failed_step)
            feedback = f"`{failed_step}` failed:\n{tail}"

        # If retries exhausted
        res = GenerationResult(
            success=False,
            branch=branch_name,
            files_changed=[str(f) for f in files],
            catalog_id=catalog_entry["id"] if catalog_entry else None,
            task_type=classification["task_type"],
            module_path=module_path,
            attempts=req.max_retries,
            failed_steps=failed_steps,
            cost_monthly_delta=monthly_cost,
            audit_verdict=final_verdict,
            error_message=f"Gave up after {req.max_retries} attempts. Last failed: {failed_steps[-1]}",
            duration_seconds=time.time() - start_time,
        )
        record_telemetry({**asdict(res), "timestamp": datetime.now(timezone.utc).isoformat(), "request": req.request})
        return res

    def reconcile(self, req: GenerationRequest) -> GenerationResult:
        """
        Drift-to-diff reconciliation mode (Phase B1).
        Takes a terraform plan or drift diff and generates corrective HCL diff.
        """
        plan_content = ""
        if req.reconcile_plan:
            p = Path(req.reconcile_plan)
            if p.exists():
                plan_content = p.read_text()
            else:
                plan_content = req.reconcile_plan

        req_text = f"reconcile drift in infrastructure: {req.request}\nPlan diff:\n{plan_content[:6000]}"
        req.request = req_text
        return self.generate(req)

    def generate_graph(self, req: GenerationRequest) -> list[GenerationResult]:
        """
        Multi-module topological generation mode (Phase C2).
        """
        client, default_model = (None, None) if req.dry_run else get_client(req.provider)
        model = req.model or default_model
        sub_modules = decompose_request(client, model, req.request, req.env, req.region)

        results = []
        print(f"🗺️  Graph mode: decomposed into {len(sub_modules)} ordered steps:")
        for idx, step in enumerate(sub_modules, start=1):
            print(f"   Step {idx}: {step['module_path']} (depends on {step.get('dependencies', [])})")

        for step in sub_modules:
            sub_req = GenerationRequest(
                request=step["request"],
                module_path=step["module_path"],
                dependencies=step.get("dependencies", []),
                env=req.env,
                region=req.region,
                provider=req.provider,
                model=req.model,
                max_retries=req.max_retries,
                skip_plan=req.skip_plan,
                no_branch=True,  # Maintain composite branch
                dry_run=req.dry_run,
                cost_threshold=req.cost_threshold,
                bypass_error_budget=req.bypass_error_budget,
            )
            res = self.generate(sub_req)
            results.append(res)
            if not res.success:
                print(f"❌ Graph execution stopped on failure in step: {step['module_path']}")
                break

        return results


# ==========================================
# 9. Local HTTP Server Mode (Phase D3)
# ==========================================
def run_server(port: int = 8000):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    agent = IaCPlatformAgent()

    class RequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, data: Any):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

        def do_GET(self):
            if self.path == "/v1/health":
                self._send_json(200, {"status": "healthy", "service": "iac-platform-agent"})
            elif self.path == "/v1/catalog":
                self._send_json(200, agent.catalog)
            elif self.path == "/v1/metrics":
                from iac_agent_metrics import load_metrics

                self._send_json(200, load_metrics())
            else:
                self._send_json(404, {"error": "Not found"})

        def do_POST(self):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return

            if self.path == "/v1/generate":
                req = GenerationRequest(**data)
                res = agent.generate(req)
                self._send_json(200 if res.success else 422, asdict(res))
            elif self.path == "/v1/reconcile":
                req = GenerationRequest(**data)
                res = agent.reconcile(req)
                self._send_json(200 if res.success else 422, asdict(res))
            else:
                self._send_json(404, {"error": "Not found"})

    # WARNING: No auth — bind to localhost only, never expose publicly
    server = HTTPServer(("127.0.0.1", port), RequestHandler)
    print(f"🚀 IaC Platform API server listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")


# ==========================================
# 10. CLI Entrypoint
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="IaC Platform Agent — Scaffolds, reconciles, and governs Terragrunt infrastructure.")
    parser.add_argument("--request", help="Natural-language description of the infra change.")
    parser.add_argument("--env", default="dev", choices=sorted(VALID_ENVS))
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--provider", choices=["gemini", "groq", "openai", "ollama"], default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--skip-plan", action="store_true", help="Skip terragrunt plan + OPA/Checkov/Trivy.")
    parser.add_argument("--no-branch", action="store_true", help="Don't create a new branch.")
    parser.add_argument("--dry-run", action="store_true", help="Scaffold only. No LLM diff, no validation.")
    parser.add_argument("--cost-threshold", type=float, default=None, help="Monthly cost threshold in USD for Infracost.")
    parser.add_argument("--reconcile", default=None, help="Path to terraform plan or drift text to reconcile.")
    parser.add_argument("--graph", action="store_true", help="Enable multi-module graph decomposition mode.")
    parser.add_argument("--bypass-error-budget", action="store_true", help="Bypass SRE production error budget gating.")
    parser.add_argument("--serve", action="store_true", help="Run local HTTP platform API server.")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP server.")
    parser.add_argument("--metrics-summary", action="store_true", help="Display health and telemetry report.")
    args = parser.parse_args()

    if args.metrics_summary:
        from iac_agent_metrics import load_metrics, print_summary

        print_summary(load_metrics())
        return

    if args.serve:
        run_server(args.port)
        return

    if not args.request:
        parser.error("--request is required unless --serve or --metrics-summary is specified.")

    req = GenerationRequest(
        request=args.request,
        env=args.env,
        region=args.region,
        provider=args.provider,
        model=args.model,
        max_retries=args.max_retries,
        skip_plan=args.skip_plan,
        no_branch=args.no_branch,
        dry_run=args.dry_run,
        cost_threshold=args.cost_threshold,
        reconcile_plan=args.reconcile,
        graph_mode=args.graph,
        bypass_error_budget=args.bypass_error_budget,
    )

    agent = IaCPlatformAgent()

    if req.graph_mode:
        results = agent.generate_graph(req)
        all_passed = all(r.success for r in results)
        if not all_passed:
            print("🛑 One or more graph steps failed.")
        sys.exit(0 if all_passed else 1)
    elif req.reconcile_plan:
        result = agent.reconcile(req)
        if not result.success and result.error_message:
            print(f"🛑 Reconciliation failed: {result.error_message}")
        sys.exit(0 if result.success else 1)
    else:
        result = agent.generate(req)
        if not result.success and result.error_message:
            print(f"🛑 Generation failed: {result.error_message}")
        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
