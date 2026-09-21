# ruff: noqa: T201, SLF001
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import asyncio
import dataclasses
import importlib.metadata
import json
import os
from pathlib import Path

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["LANGSMITH_TRACING"] = "false"
ROOT = Path(__file__).parent
FOCUSED = ["get_file_contents", "search_code", "issue_read"]
ENV = {"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"}
COMMAND = str(ROOT / "github/github-mcp-server")
OUT = ROOT / "framework-payloads"
OUT.mkdir(exist_ok=True)


def save(name, payload):
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(name)


async def langchain():
    from fastmcp.client.transports import StdioTransport
    from langchain.agents import create_agent
    from langchain.agents.middleware import ProviderToolSearchMiddleware
    from langchain.mcp import MCPAdapter
    from langchain_anthropic import ChatAnthropic
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    async with MCPAdapter(
        StdioTransport(command=COMMAND, args=["stdio", "--exclude-tools=delete_repository"], env=ENV)
    ) as adapter:
        tools = await adapter.list_tools()
    # Provider serialization; invoke is not called and no model request is sent.
    model = ChatAnthropic(model="claude-sonnet-4-6", api_key="dummy", max_tokens=1)
    for mode, subset in [("eager", tools), ("focused", [t for t in tools if t.name in FOCUSED])]:
        bound = model.bind_tools(subset)
        save(
            f"langchain-{mode}",
            model._get_request_payload(
                [HumanMessage(content="Inspect a GitHub issue and its source.")], **bound.kwargs
            ),
        )

    # Execute create_agent's LangGraph with a capture model to inspect actual bindings.
    class CaptureModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **_kwargs):
            save("langgraph-bound-tools", model.bind_tools(tools).kwargs)
            return self

    graph = create_agent(CaptureModel(responses=[AIMessage(content="captured")]), tools=tools)
    await graph.ainvoke({"messages": [HumanMessage(content="Inspect a GitHub issue and its source.")]})

    # Run the provider middleware with a capture handler at the model boundary.
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    middleware = ProviderToolSearchMiddleware(searchable_tools=[t.name for t in tools])
    request = ModelRequest(
        model=model, tools=tools, messages=[HumanMessage(content="Inspect a GitHub issue and its source.")]
    )

    def capture(request):
        bound = model.bind_tools(request.tools)
        save("langchain-provider-search", model._get_request_payload(request.messages, **bound.kwargs))
        return ModelResponse(result=[AIMessage(content="captured")])

    middleware.wrap_model_call(request, capture)

    from langchain.agents.middleware import LLMToolSelectorMiddleware
    from langchain_core.runnables import RunnableLambda

    class SelectorModel(FakeMessagesListChatModel):
        def with_structured_output(self, schema, **_kwargs):
            def select(messages, **_kwargs):
                save(
                    "langchain-selector-request",
                    {
                        "response_schema": schema,
                        "messages": [m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in messages],
                    },
                )
                return {"tools": FOCUSED}

            return RunnableLambda(select)

    selector = LLMToolSelectorMiddleware(model=SelectorModel(responses=[]), max_tools=3)

    def selected_capture(request):
        bound = model.bind_tools(request.tools)
        save("langchain-selector-main", model._get_request_payload(request.messages, **bound.kwargs))
        return ModelResponse(result=[AIMessage(content="captured")])

    selector.wrap_model_call(request, selected_capture)


async def adk():
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    from mcp import StdioServerParameters

    for mode, selected in [("eager", None), ("focused", FOCUSED)]:
        toolset = McpToolset(
            connection_params=StdioServerParameters(
                command=COMMAND, args=["stdio", "--exclude-tools=delete_repository"], env=ENV
            ),
            tool_filter=selected,
        )
        try:
            tools = await toolset.get_tools()
            save(
                f"adk-{mode}",
                {
                    "function_declarations": [
                        t._get_declaration().model_dump(mode="json", by_alias=True, exclude_none=True) for t in tools
                    ]
                },
            )
        finally:
            await toolset.close()


async def pydantic_ai():
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai import Agent
    from pydantic_ai.mcp import MCPToolset
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    class LocalFunctionModel(FunctionModel):
        @classmethod
        def supported_native_tools(cls):
            return frozenset()

    for mode in ["eager", "focused", "deferred"]:
        toolset = MCPToolset(
            StdioTransport(command=COMMAND, args=["stdio", "--exclude-tools=delete_repository"], env=ENV)
        )
        selected = toolset
        if mode == "focused":
            selected = toolset.filtered(lambda _ctx, tool: tool.name in FOCUSED)
        if mode == "deferred":
            selected = toolset.defer_loading()

        def capture(messages, info, _mode=mode):
            save(
                f"pydantic-{_mode}",
                {
                    "tools": [dataclasses.asdict(t) for t in info.function_tools],
                    "messages": [dataclasses.asdict(m) for m in messages],
                },
            )
            return ModelResponse(parts=[TextPart(content="captured")])

        agent = Agent(LocalFunctionModel(capture), toolsets=[selected])
        await agent.run("Inspect a GitHub issue and its source.")


async def main():
    save(
        "versions",
        {
            p: importlib.metadata.version(p)
            for p in [
                "langchain",
                "langgraph",
                "langchain-mcp-adapters",
                "langchain-anthropic",
                "google-adk",
                "pydantic-ai-slim",
                "mcp",
                "tiktoken",
            ]
        },
    )
    import sys

    for fn in [langchain, adk, pydantic_ai]:
        if len(sys.argv) > 1 and fn.__name__ not in sys.argv[1:]:
            continue
        try:
            await fn()
        except Exception as e:
            import traceback

            traceback.print_exc()
            save(f"{fn.__name__}-error", {"type": type(e).__name__, "message": str(e)})


asyncio.run(main())
