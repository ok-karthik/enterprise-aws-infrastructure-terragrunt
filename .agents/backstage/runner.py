#!/usr/bin/env python3
"""
Backstage Scaffolder Action Bridge for IaC Generation Agent (Phase D2 / PLAN.md).

Allows Backstage / IDP Scaffolder actions to execute infrastructure generation
requests deterministically, returning machine-readable JSON results.

Usage:
  python3 .agents/backstage/runner.py --input-json '{"request": "add an s3 bucket", "env": "dev"}'
"""

import argparse
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent  # .agents/
sys.path.insert(0, str(BASE_DIR / "scripts"))

from iac_agent import GenerationRequest, IaCPlatformAgent  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Backstage Scaffolder Runner for IaC Platform Agent.")
    parser.add_argument("--input-json", help="JSON string of Backstage template inputs.")
    parser.add_argument("--request", help="Natural language request string.")
    parser.add_argument("--env", default="dev")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--provider", default="gemini")
    parser.add_argument("--skip-plan", action="store_true")
    args = parser.parse_args()

    payload = {}
    if args.input_json:
        try:
            payload = json.loads(args.input_json)
        except json.JSONDecodeError as e:
            sys.exit(f"❌ Failed to parse input-json: {e}")

    request_text = payload.get("request") or args.request
    if not request_text:
        sys.exit("❌ Error: request is required either via --request or --input-json.")

    req = GenerationRequest(
        request=request_text,
        env=payload.get("env") or args.env,
        region=payload.get("region") or args.region,
        provider=payload.get("provider") or args.provider,
        skip_plan=payload.get("skip_plan", args.skip_plan),
        dry_run=payload.get("dry_run", False),
    )

    agent = IaCPlatformAgent()
    result = agent.generate(req)

    output = {
        "success": result.success,
        "branch_name": result.branch,
        "branch_url": f"https://github.com/ok-karthik/enterprise-aws-infrastructure-terragrunt/tree/{result.branch}" if result.branch else None,
        "catalog_id": result.catalog_id,
        "files_changed": [str(p) for p in result.files_changed],
        "attempts": result.attempts,
        "error_message": result.error_message,
    }
    print(json.dumps(output, indent=2))
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
