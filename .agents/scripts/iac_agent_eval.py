#!/usr/bin/env python3
"""
Eval harness for the IaC Generation Agent's classification step (Phase A4 / PLAN.md).

Runs a fixed set of fixtures (.agents/eval/fixtures.yaml) through the exact same
catalog-match -> LLM-classify path main() uses in iac_agent.py, and checks the result
against what each fixture expects. Catalog-hit fixtures are fully offline and
deterministic (no API key needed, no network call); LLM-fallback fixtures are skipped
(not failed) when no provider/API key is configured, so this is safe to run anywhere,
including CI without secrets — and gives a fast regression check when swapping models
(e.g. benchmarking Gemini Flash vs. Groq vs. a local Ollama model) or editing prompts.

Usage:
  python3 .agents/scripts/iac_agent_eval.py [--provider gemini]
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iac_agent  # noqa: E402

FIXTURES_PATH = Path(__file__).resolve().parent.parent / "eval" / "fixtures.yaml"


def load_fixtures() -> list[dict]:
    import yaml

    return yaml.safe_load(FIXTURES_PATH.read_text()) or []


def run_fixture(fixture: dict, catalog: list[dict], client, model: Optional[str]) -> tuple[Optional[bool], str]:
    request = fixture["request"]
    entry = iac_agent.match_catalog(request, catalog)

    if "expect_catalog_id" in fixture:
        if entry and entry["id"] == fixture["expect_catalog_id"]:
            return True, f"catalog match: {entry['id']}"
        got = entry["id"] if entry else "(no match)"
        return False, f"expected catalog id {fixture['expect_catalog_id']!r}, got {got!r}"

    if entry:
        return False, f"expected no catalog match (LLM classification fixture), but matched {entry['id']!r}"

    if client is None:
        return None, "skipped — no LLM provider/API key configured for this fixture"

    classification = iac_agent.classify_request(client, model, request, "dev", "eu-central-1")
    if "expect_task_type" in fixture and classification.get("task_type") != fixture["expect_task_type"]:
        return False, f"expected task_type {fixture['expect_task_type']!r}, got {classification.get('task_type')!r}"
    prefix = fixture.get("expect_module_path_prefix")
    if prefix and not classification.get("module_path", "").startswith(prefix):
        return False, f"expected module_path to start with {prefix!r}, got {classification.get('module_path')!r}"
    return True, f"classified: {classification}"


def main():
    parser = argparse.ArgumentParser(description="Eval harness for iac_agent.py classification.")
    parser.add_argument("--provider", choices=["gemini", "groq", "openai", "ollama"], default="gemini")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    fixtures = load_fixtures()
    catalog = iac_agent.load_catalog()

    client, default_model = None, None
    try:
        client, default_model = iac_agent.get_client(args.provider)
    except SystemExit:
        client = None
    model = args.model or default_model

    passed = failed = skipped = 0
    for fixture in fixtures:
        result, detail = run_fixture(fixture, catalog, client, model)
        if result is None:
            skipped += 1
            print(f"⏭️  SKIP  {fixture['request']!r} — {detail}")
        elif result:
            passed += 1
            print(f"✅ PASS  {fixture['request']!r} — {detail}")
        else:
            failed += 1
            print(f"❌ FAIL  {fixture['request']!r} — {detail}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped ({len(fixtures)} total)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
