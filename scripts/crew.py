# ruff: noqa: T201
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import json
import os
from pathlib import Path

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_DISABLED"] = "true"

from crewai.mcp.config import MCPServerStdio
from crewai.mcp.filters import create_static_tool_filter
from crewai.mcp.tool_resolver import MCPToolResolver
from crewai.utilities.logger import Logger

ROOT = Path(__file__).parent
for mode in ["eager", "focused"]:
    config = MCPServerStdio(
        command="github-mcp-server",
        args=["stdio"],
        env={
            "GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only",
            "PATH": str(ROOT / "github") + os.pathsep + os.environ["PATH"],
        },
        tool_filter=create_static_tool_filter(allowed_tool_names=["get_file_contents", "search_code", "issue_read"])
        if mode == "focused"
        else None,
    )
    resolver = MCPToolResolver(agent=None, logger=Logger())
    try:
        tools = resolver.resolve([config])
        data = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.args_schema.model_json_schema(),
                "original_name": t.original_tool_name,
            }
            for t in tools
        ]
        (ROOT / "framework-payloads" / f"crewai-{mode}.json").write_text(json.dumps(data, indent=2) + "\n")
        print(mode, len(tools))
    finally:
        resolver.cleanup()
