# ruff: noqa: T201
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).parent


async def main():
    modes = {
        "default": [],
        "all": ["--toolsets=all"],
        "read_only": ["--read-only"],
        "focused": ["--toolsets=", "--tools=get_file_contents,search_code,issue_read"],
    }
    for name, flags in modes.items():
        params = StdioServerParameters(
            command=str(ROOT / "github/github-mcp-server"),
            args=["stdio", *flags],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            tools = []
            cursor = None
            while True:
                response = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
                tools.extend(t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in response.tools)
                cursor = response.next_cursor
                if not cursor:
                    break
            data = {"initialize": init.model_dump(mode="json", by_alias=True, exclude_none=True), "tools": tools}
            (ROOT / f"github-{name}.json").write_text(json.dumps(data, indent=2) + "\n")
            print(name, len(tools))


asyncio.run(main())
