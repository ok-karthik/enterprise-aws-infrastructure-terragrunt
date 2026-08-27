#!/usr/bin/env python3
"""
Health & Telemetry metrics for the IaC Generation Agent (Phase D4 / PLAN.md).

Parses the append-only telemetry log (.agents/metrics/runs.jsonl) to provide
Platform Engineering and SRE teams with empirical visibility into:
1. Overall agent success rate and retry efficiency
2. Golden-path catalog hit rate vs. free-form LLM generation
3. Validation ladder failure step distribution (identifying where guardrails catch issues)
4. Cost impacts and high-demand module types
"""

from collections import Counter
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
METRICS_PATH = BASE_DIR / "metrics" / "runs.jsonl"


def load_metrics(path: Path = METRICS_PATH) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def print_summary(records: list[dict]):
    if not records:
        print("📊 No metrics recorded yet. Runs will log to .agents/metrics/runs.jsonl automatically.")
        return

    total = len(records)
    successes = sum(1 for r in records if r.get("success"))
    failures = total - successes
    success_rate = (successes / total) * 100 if total else 0

    catalog_runs = [r for r in records if r.get("catalog_id")]
    llm_runs = [r for r in records if not r.get("catalog_id")]

    cat_successes = sum(1 for r in catalog_runs if r.get("success"))
    cat_rate = (cat_successes / len(catalog_runs) * 100) if catalog_runs else 0

    llm_successes = sum(1 for r in llm_runs if r.get("success"))
    llm_rate = (llm_successes / len(llm_runs) * 100) if llm_runs else 0

    avg_attempts = sum(r.get("attempts", 1) for r in records) / total if total else 0

    failed_steps = Counter()
    for r in records:
        for step in r.get("failed_steps", []):
            failed_steps[step] += 1

    modules = Counter(r.get("module_path", "unknown") for r in records)

    print("==========================================================")
    print("📈 IaC Generation Agent — Platform Health & Reliability")
    print("==========================================================")
    print(f"Total Requests Processed:     {total}")
    print(f"Overall Success Rate:         {success_rate:.1f}% ({successes} succeeded, {failures} failed)")
    print(f"Average Attempts Per Run:     {avg_attempts:.2f}")
    print("\n--- Golden Path vs Free-form Generation ---")
    print(f"Catalog (Pre-vetted) Runs:    {len(catalog_runs)} ({cat_rate:.1f}% success)")
    print(f"Free-form (LLM HCL) Runs:     {len(llm_runs)} ({llm_rate:.1f}% success)")

    print("\n--- Validation Ladder Failure Distribution ---")
    if failed_steps:
        for step, count in failed_steps.most_common():
            print(f"  ❌ {step:<25} : {count} occurrences")
    else:
        print("  ✨ Zero validation ladder failures recorded.")

    print("\n--- Top Requested Modules ---")
    for mod, count in modules.most_common(5):
        print(f"  📦 {mod:<25} : {count} requests")
    print("==========================================================")


def main():
    records = load_metrics()
    print_summary(records)


if __name__ == "__main__":
    main()
