# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pydantic-ai-slim[google,mcp]==2.55.0",
#   "google-genai==2.29.0",
#   "fastmcp-slim==4.1.0",
#   "mcp==2.3.0",
# ]
# ///
"""PydanticAI agent: `Agent` with an `MCPToolset` over stdio.

eager lists every tool; allowlist uses `toolset.filtered(...)`; search uses
`toolset.defer_loading()`, which hides every tool behind PydanticAI's local `search_tools`
function because Gemini has no provider-native tool search.
"""

import warnings

from fastmcp.client.transports import StdioTransport
from frameworks import LOCATION, MAX_MODEL_CALLS, MODEL, PROJECT, SHELL_DESCRIPTION, Context, main
from google import genai
from pydantic_ai import Agent, Tool
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.usage import UsageLimits

warnings.filterwarnings("ignore")


async def run(ctx: Context) -> str:
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    model = GoogleModel(MODEL, provider=GoogleProvider(client=client))
    settings = GoogleModelSettings(google_thinking_config={"thinking_level": "low"})
    toolsets, tools = [], []
    if ctx.mcp_command:
        toolset = MCPToolset(StdioTransport(command=ctx.mcp_command[0], args=ctx.mcp_command[1:]))
        if ctx.allowlist:
            allowed = set(ctx.allowlist)
            toolset = toolset.filtered(lambda _ctx, tool: tool.name in allowed)
        if ctx.condition == "search":
            toolset = toolset.defer_loading()
        toolsets = [toolset]
    if ctx.condition == "cli":
        tools = [Tool(ctx.shell, name="run_shell", description=SHELL_DESCRIPTION)]
    agent = Agent(model, toolsets=toolsets, tools=tools, instructions=ctx.instructions or None, model_settings=settings)
    result = await agent.run(ctx.prompt, usage_limits=UsageLimits(request_limit=MAX_MODEL_CALLS))
    return result.output


if __name__ == "__main__":
    main("pydantic", ["pydantic-ai-slim", "google-genai", "mcp", "fastmcp-slim"], run)
