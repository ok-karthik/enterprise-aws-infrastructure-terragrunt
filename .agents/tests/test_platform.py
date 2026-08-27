#!/usr/bin/env python3
"""
Unit and regression tests for the IaC Platform Agent core functionality.
Safe to run offline without AWS credentials or API keys.
"""

from pathlib import Path
import tempfile
import unittest

# Import agent modules
BASE_DIR = Path(__file__).resolve().parent.parent  # .agents/
import sys
sys.path.insert(0, str(BASE_DIR / "scripts"))

import iac_agent  # noqa: E402
from mcp_client import MCPClient  # noqa: E402
import iac_agent_metrics  # noqa: E402


class TestIaCPlatformAgent(unittest.TestCase):
    def setUp(self):
        self.catalog = iac_agent.load_catalog()

    def test_catalog_loaded(self):
        self.assertTrue(len(self.catalog) >= 3)
        ids = [entry["id"] for entry in self.catalog]
        self.assertIn("data/s3-encrypted", ids)
        self.assertIn("data/rds-postgres", ids)
        self.assertIn("data/dynamodb-table", ids)

    def test_catalog_matching(self):
        s3_match = iac_agent.match_catalog("Create an S3 bucket for build artifacts", self.catalog)
        self.assertIsNotNone(s3_match)
        self.assertEqual(s3_match["id"], "data/s3-encrypted")

        rds_match = iac_agent.match_catalog("Provision an RDS postgres database instance", self.catalog)
        self.assertIsNotNone(rds_match)
        self.assertEqual(rds_match["id"], "data/rds-postgres")

    def test_sre_error_budget_dev(self):
        # Dev should always pass
        ok, msg = iac_agent.check_sre_error_budget("dev")
        self.assertTrue(ok)

    def test_sre_error_budget_prod_exhaustion(self):
        import os

        # Normal prod should pass by default
        ok, _ = iac_agent.check_sre_error_budget("prod")
        self.assertTrue(ok)

        # Simulating budget exhaustion (<10%)
        os.environ["SLO_ERROR_BUDGET_REMAINING"] = "4.2"
        try:
            ok, msg = iac_agent.check_sre_error_budget("prod", bypass=False)
            self.assertFalse(ok)
            self.assertIn("Exhausted", msg)

            # Bypass flag overrides
            ok_bypass, _ = iac_agent.check_sre_error_budget("prod", bypass=True)
            self.assertTrue(ok_bypass)
        finally:
            del os.environ["SLO_ERROR_BUDGET_REMAINING"]

    def test_mcp_client_graceful_fallback(self):
        client = MCPClient(endpoint_url="http://127.0.0.1:59999/mcp")
        self.assertFalse(client.is_available())
        doc = client.get_provider_doc("aws_s3_bucket")
        self.assertIsNone(doc)

    def test_graph_decomposition_heuristic(self):
        # Offline heuristic test when no LLM client is available
        modules = iac_agent.decompose_request(
            None, None, "stand up microservice environment: VPC + EKS + RDS", "dev", "eu-central-1"
        )
        paths = [m["module_path"] for m in modules]
        self.assertIn("network/vpc", paths)
        self.assertIn("compute/eks", paths)
        self.assertIn("data/rds-postgres", paths)

    def test_metrics_telemetry(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl") as tf:
            metrics_path = Path(tf.name)
            event = {
                "success": True,
                "request": "test request",
                "module_path": "storage/test",
                "catalog_id": "test-cat",
                "attempts": 1,
            }
            def _write(ev):
                with metrics_path.open("a") as f:
                    f.write(iac_agent.json.dumps(ev) + "\n")

            iac_agent.record_telemetry = _write
            iac_agent.record_telemetry(event)

            records = iac_agent_metrics.load_metrics(metrics_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["module_path"], "storage/test")

    def test_dry_run_no_side_effects(self):
        import subprocess

        initial_branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=iac_agent.REPO_ROOT, text=True
        ).strip()
        req = iac_agent.GenerationRequest(
            request="add an S3 bucket for test artifacts",
            env="dev",
            region="eu-central-1",
            dry_run=True,
        )
        agent = iac_agent.IaCPlatformAgent(self.catalog)
        res = agent.generate(req)
        self.assertTrue(res.success)
        self.assertIsNone(res.branch)

        # Verify branch did not change
        current_branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=iac_agent.REPO_ROOT, text=True
        ).strip()
        self.assertEqual(initial_branch, current_branch)

        # Verify no files were created on disk
        for f in res.files_changed:
            self.assertFalse(Path(f).exists(), f"File should not have been created in dry-run: {f}")

    def test_change_window_parsing(self):
        from datetime import datetime, timezone

        windows = ["Mon-Thu 08:00-16:00 UTC"]

        # Tuesday 10:00 UTC (In window: weekday 1)
        dt_in = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(iac_agent.is_in_change_window(dt_in, windows))

        # Friday 10:00 UTC (Outside window: weekday 4)
        dt_wrong_day = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
        self.assertFalse(iac_agent.is_in_change_window(dt_wrong_day, windows))

        # Wednesday 20:00 UTC (Outside window: wrong hour)
        dt_wrong_time = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
        self.assertFalse(iac_agent.is_in_change_window(dt_wrong_time, windows))

    def test_change_window_enforcement(self):
        from datetime import datetime, timezone
        import os

        # Outside window on Saturday at 03:00 UTC
        dt_sat = datetime(2026, 8, 29, 3, 0, tzinfo=timezone.utc)

        # Default: advisory only (enforce_change_windows is false)
        ok, msg = iac_agent.check_sre_error_budget("prod", now=dt_sat)
        self.assertTrue(ok)

        # When ENFORCE_CHANGE_WINDOWS=1: blocked
        os.environ["ENFORCE_CHANGE_WINDOWS"] = "1"
        try:
            ok, msg = iac_agent.check_sre_error_budget("prod", now=dt_sat)
            self.assertFalse(ok)
            self.assertIn("Change Window Restriction", msg)
        finally:
            del os.environ["ENFORCE_CHANGE_WINDOWS"]

    def test_dynamodb_template_scaffolding(self):
        entry = iac_agent.match_catalog("provision a dynamodb table for sessions", self.catalog)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "data/dynamodb-table")
        self.assertEqual(entry["template"], "data-dynamodb-table")
        template_file = iac_agent.CATALOG_TEMPLATES_DIR / entry["template"] / "envcommon.hcl.tmpl"
        self.assertTrue(template_file.exists())
        tmpl_content = template_file.read_text()
        self.assertIn("terraform-aws-modules/dynamodb-table/aws", tmpl_content)
        self.assertIn("PAY_PER_REQUEST", tmpl_content)


if __name__ == "__main__":
    unittest.main()
