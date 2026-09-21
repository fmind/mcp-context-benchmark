# ruff: noqa: T201
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import asyncio
import json
import os
from pathlib import Path

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
os.environ["OTEL_SDK_DISABLED"] = "true"

import httpx2
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

ROOT = Path(__file__).parent


async def main():
    for mode in ["eager", "focused", "deferred"]:

        def handler(request, _mode=mode):
            payload = json.loads(request.content)
            (ROOT / "framework-payloads" / f"pydantic-wire-{_mode}.json").write_text(
                json.dumps(payload, indent=2) + "\n"
            )
            return httpx2.Response(
                200,
                json={
                    "id": "local-capture",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": "Captured locally, no inference."}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            )

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        provider = AnthropicProvider(api_key="dummy", http_client=client)
        model = AnthropicModel("claude-sonnet-4-6", provider=provider)
        toolset = MCPToolset(
            StdioTransport(
                command=str(ROOT / "github/github-mcp-server"),
                args=["stdio", "--exclude-tools=delete_repository"],
                env={"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"},
            )
        )
        selected = toolset
        if mode == "focused":
            selected = toolset.filtered(lambda _ctx, t: t.name in ["get_file_contents", "search_code", "issue_read"])
        if mode == "deferred":
            selected = toolset.defer_loading()
        await Agent(model, toolsets=[selected]).run("Inspect a GitHub issue and its source.")
        await client.aclose()
        print(mode)


asyncio.run(main())
