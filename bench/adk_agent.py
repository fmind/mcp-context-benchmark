# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "google-adk[mcp]==2.11.0",
#   "google-genai==2.29.0",
#   "mcp==2.3.0",
# ]
# ///
"""Google ADK agent: `LlmAgent` with an `McpToolset`, run by `InMemoryRunner`.

eager lists every tool; allowlist uses `McpToolset(tool_filter=...)`. ADK has no
tool-search or deferred-loading option for MCP tools, so it has no search condition.
"""

import logging
import warnings

from frameworks import CONDITIONS, MAX_MODEL_CALLS, MODEL, Context, main
from google.adk.agents import LlmAgent, RunConfig
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)


async def run(ctx: Context) -> str:
    tools, toolset = [], None
    if ctx.mcp_command:
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(command=ctx.mcp_command[0], args=ctx.mcp_command[1:]),
                timeout=60,
            ),
            tool_filter=ctx.allowlist,
        )
        tools = [toolset]
    if ctx.condition == "cli":

        async def run_shell(command: str) -> str:
            """Run a bash command in the workspace and return its exit code, stdout, and stderr."""
            return await ctx.shell(command)

        tools = [FunctionTool(run_shell)]
    agent = LlmAgent(
        name="github_agent",
        model=MODEL,
        instruction=ctx.instructions,
        tools=tools,
        generate_content_config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
        ),
    )
    runner = InMemoryRunner(agent=agent, app_name="benchmark")
    session = await runner.session_service.create_session(app_name="benchmark", user_id="benchmark")
    final = ""
    try:
        async for event in runner.run_async(
            user_id="benchmark",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=ctx.prompt)]),
            run_config=RunConfig(max_llm_calls=MAX_MODEL_CALLS),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final = "".join(p.text or "" for p in event.content.parts if not p.thought)
    finally:
        if toolset:
            await toolset.close()
    return final


if __name__ == "__main__":
    main("adk", ["google-adk", "google-genai", "mcp"], run, tuple(c for c in CONDITIONS if c != "search"))
