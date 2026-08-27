#!/usr/bin/env python3
"""
Lightweight MCP (Model Context Protocol) client for the IaC Generation Agent.

Connects to the terraform-mcp service defined in .agents/mcp/docker-compose.yml
via Streamable-HTTP / JSON-RPC 2.0, providing live schema and doc retrieval
from the Terraform Registry.

If the MCP server is not running, all methods fail gracefully and return None,
allowing the agent to seamlessly fall back to its zero-dependency GitHub raw doc scraper.
"""

import json
import os
from typing import Any, Optional
import urllib.error
import urllib.request


DEFAULT_MCP_URL = os.getenv("MCP_TERRAFORM_URL", "http://localhost:8080/mcp")


class MCPClient:
    """Client for HashiCorp terraform-mcp server."""

    def __init__(self, endpoint_url: str = DEFAULT_MCP_URL, timeout: float = 3.0):
        self.endpoint_url = endpoint_url
        self.timeout = timeout

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Optional[str]:
        """
        Execute an MCP tool call via JSON-RPC 2.0.
        Returns the text content of the tool response, or None if unavailable.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    result = body.get("result", {})
                    content_list = result.get("content", [])
                    texts = [item.get("text", "") for item in content_list if item.get("type") == "text"]
                    return "\n\n".join(texts).strip() or None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None
        return None

    def get_provider_doc(self, resource_hint: str, provider: str = "hashicorp/aws") -> Optional[str]:
        """Query terraform-mcp for a resource schema/documentation."""
        if not resource_hint:
            return None
        # Try get_provider_doc or get_resource_doc
        doc = self.call_tool("get_provider_doc", {"provider": provider, "resource": resource_hint})
        if not doc:
            doc = self.call_tool("search_registry", {"query": resource_hint, "type": "resource"})
        return doc

    def is_available(self) -> bool:
        """Check if the MCP server is reachable."""
        try:
            # Check root health or ping
            health_url = self.endpoint_url.rsplit("/", 1)[0] + "/health"
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False
