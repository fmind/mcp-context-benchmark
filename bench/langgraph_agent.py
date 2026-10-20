# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "langchain==1.4.4",
#   "langgraph==1.2.14",
#   "langchain-mcp-adapters==0.3.2",
#   "langchain-google-genai==4.4.0",
#   "google-genai==2.29.0",
#   "mcp==1.30.0",
# ]
# ///
"""LangGraph agent: `create_agent` with MCP tools from `langchain-mcp-adapters`.

eager binds every listed tool; allowlist keeps three by name; search adds LangChain's
`LLMToolSelectorMiddleware`, which asks the model to pick at most three tools before each
model call. LangChain's provider-native tool search supports only Anthropic and OpenAI.
"""

import warnings

from frameworks import LOCATION, MAX_MODEL_CALLS, MODEL, PROJECT, SHELL_DESCRIPTION, Context, main
from langchain.agents import create_agent
from langchain.agents.middleware import LLMToolSelectorMiddleware
from langchain_core.tools import StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

warnings.filterwarnings("ignore")


async def run(ctx: Context) -> str:
    model = ChatGoogleGenerativeAI(
        model=MODEL, vertexai=True, project=PROJECT, location=LOCATION, thinking_level="low", max_retries=0
    )
    tools, middleware = [], []
    if ctx.mcp_command:
        client = MultiServerMCPClient(
            {"github": {"transport": "stdio", "command": ctx.mcp_command[0], "args": ctx.mcp_command[1:]}}
        )
        tools = await client.get_tools()
        if ctx.allowlist:
            tools = [t for t in tools if t.name in ctx.allowlist]
    if ctx.condition == "search":
        middleware.append(LLMToolSelectorMiddleware(model=model, max_tools=3))
    if ctx.condition == "cli":
        tools = [StructuredTool.from_function(coroutine=ctx.shell, name="run_shell", description=SHELL_DESCRIPTION)]
    agent = create_agent(model, tools=tools, system_prompt=ctx.instructions or None, middleware=middleware)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": ctx.prompt}]}, {"recursion_limit": 2 * MAX_MODEL_CALLS + 1}
    )
    return result["messages"][-1].text


if __name__ == "__main__":
    main(
        "langgraph",
        ["langchain", "langgraph", "langchain-mcp-adapters", "langchain-google-genai", "google-genai", "mcp"],
        run,
    )
