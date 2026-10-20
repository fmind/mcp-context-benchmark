"""Shared harness for the framework agents: workspace, tools, usage capture, and the record.

Each framework script (`langgraph_agent.py`, `adk_agent.py`, `pydantic_agent.py`) declares its
own pinned dependencies and calls `main(...)` with one coroutine that builds the agent the
framework's documented way and returns its final text. Everything else is identical:

- the model is Gemini 3.8 Flash on Vertex AI (`global`), thinking level low;
- usage is read from every google-genai response, the client all three frameworks use, so
  framework-internal calls such as a tool selector are counted like any other model call;
- HTTP 429/5xx responses are retried with backoff and counted; they carry no usage;
- the CLI condition gets one shell tool in the run workspace, with the read-only `gh` shim
  first on PATH, and the `gh` skill listed in the instructions by name and description.

Usage: <framework>_agent.py <out-dir> <condition> <task> <rep>
"""

import asyncio
import functools
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import common
from google.genai import errors, models

MODEL = "gemini-3.8-flash"
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = "global"
CONDITIONS = ("none", "eager", "search", "allowlist", "cli")
MAX_MODEL_CALLS = 25
SHELL_TIMEOUT = 60
SHELL_LIMIT = 30_000
SHELL_DESCRIPTION = "Run a bash command in the workspace and return its exit code, stdout, and stderr."
SKILL_LISTING = """Skills are folders of instructions for specific tools. Read a skill's SKILL.md before using its tool.
Available skills:
- gh: {description} (skills/gh/SKILL.md)"""
RETRYABLE = {429, 500, 502, 503, 504}


@dataclass
class Context:
    """Everything a framework script needs to build its agent for one run."""

    condition: str
    prompt: str
    instructions: str
    mcp_command: list[str] | None
    allowlist: list[str] | None
    work: Path
    shell_env: dict = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)

    async def shell(self, command: str) -> str:
        """Run one command in the workspace; the transcript feeds the outside-path audit."""
        self.commands.append(command)
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", command, cwd=self.work, env=self.shell_env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
        try:
            out, err = await asyncio.wait_for(proc.communicate(), SHELL_TIMEOUT)
        except TimeoutError:
            proc.kill()
            return f"exit_code: timeout after {SHELL_TIMEOUT}s"
        text = f"exit_code: {proc.returncode}\nstdout:\n{out.decode(errors='replace')}\nstderr:\n{err.decode(errors='replace')}"
        self.transcript.append(command + "\n" + text)
        return text if len(text) <= SHELL_LIMIT else text[:SHELL_LIMIT] + f"\n[truncated at {SHELL_LIMIT} characters]"


CALLS: list[dict] = []
FIRST_TOOLS: list = []


def _declarations(request_tools: object) -> list[dict]:
    """Function declarations exactly as the framework handed them to google-genai, as JSON."""
    found = []
    for tool in request_tools or []:
        if hasattr(tool, "model_dump"):
            tool = tool.model_dump(mode="json", exclude_none=True)
        if isinstance(tool, dict):
            found += tool.get("function_declarations") or tool.get("functionDeclarations") or []
    return [d.model_dump(mode="json", exclude_none=True) if hasattr(d, "model_dump") else d for d in found]


def _record(response: object, request_tools: object, retries: int) -> None:
    usage = getattr(response, "usage_metadata", None)
    declared = _declarations(request_tools)
    if not CALLS:
        FIRST_TOOLS.extend(declared)
    declarations = len(declared)
    CALLS.append(
        {
            "input": getattr(usage, "prompt_token_count", None),
            "cache_read": getattr(usage, "cached_content_token_count", None),
            "output": getattr(usage, "candidates_token_count", None),
            "reasoning": getattr(usage, "thoughts_token_count", None),
            "declared_functions": declarations,
            "model_version": getattr(response, "model_version", None),
            "retries": retries,
        }
    )


def _tools_of(kwargs: dict) -> object:
    config = kwargs.get("config")
    return config.get("tools") if isinstance(config, dict) else getattr(config, "tools", None)


async def _retry_async(call: Callable[[], Awaitable]) -> tuple[object, int]:
    for attempt in range(6):
        try:
            return await call(), attempt
        except errors.APIError as error:
            if error.code not in RETRYABLE or attempt == 5:
                raise
            await asyncio.sleep(min(60, 5 * 2**attempt))
    raise AssertionError("unreachable")


def _patch_genai() -> None:
    """Count usage on every google-genai call, whatever the framework, and retry transient errors."""
    original = models.AsyncModels.generate_content
    original_stream = models.AsyncModels.generate_content_stream

    @functools.wraps(original)
    async def generate_content(self, *args, **kwargs):
        response, retries = await _retry_async(lambda: original(self, *args, **kwargs))
        _record(response, _tools_of(kwargs), retries)
        return response

    @functools.wraps(original_stream)
    async def generate_content_stream(self, *args, **kwargs):
        stream, retries = await _retry_async(lambda: original_stream(self, *args, **kwargs))

        async def chunks():
            last = None
            async for chunk in stream:
                last = chunk if getattr(chunk, "usage_metadata", None) else last
                yield chunk
            _record(last, _tools_of(kwargs), retries)

        return chunks()

    sync_original = models.Models.generate_content

    @functools.wraps(sync_original)
    def sync_generate_content(self, *args, **kwargs):
        for attempt in range(6):
            try:
                response = sync_original(self, *args, **kwargs)
                break
            except errors.APIError as error:
                if error.code not in RETRYABLE or attempt == 5:
                    raise
                time.sleep(min(60, 5 * 2**attempt))
        _record(response, _tools_of(kwargs), attempt)
        return response

    models.AsyncModels.generate_content = generate_content
    models.AsyncModels.generate_content_stream = generate_content_stream
    models.Models.generate_content = sync_generate_content


def _skill_description() -> str:
    text = (common.HERE / "skills" / "gh" / "SKILL.md").read_text()
    line = next(line for line in text.splitlines() if line.startswith("description:"))
    return line.split(":", 1)[1].strip().strip('"')


def main(
    agent: str, packages: list[str], run_agent: Callable[[Context], Awaitable[str]], conditions=CONDITIONS
) -> None:
    out, condition, task, rep = sys.argv[1:]
    if condition not in conditions or task not in common.TASKS:
        sys.exit(f"invalid condition or task; {agent} supports {', '.join(conditions)}")
    if not PROJECT:
        sys.exit("set GOOGLE_CLOUD_PROJECT to the Vertex AI project to bill")
    os.environ |= {
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_CLOUD_LOCATION": LOCATION,
        "OTEL_SDK_DISABLED": "true",
        "LANGSMITH_TRACING": "false",
    }
    _patch_genai()
    run, work = common.prepare(out, agent, condition, task, rep)
    ctx = Context(
        condition=condition,
        prompt=common.prompt(task, condition),
        instructions="",
        mcp_command=common.server_command(condition, run / "log" / "gate.jsonl", common.DEFAULT_ARGS),
        allowlist=common.ROLE_TOOLS if condition == "allowlist" else None,
        work=work,
        shell_env={"PATH": f"{run / 'bin'}:/usr/local/bin:/usr/bin:/bin", "HOME": str(run), "LANG": "C.UTF-8"},
    )
    if condition == "cli":
        common.install_skill(work / "skills")
        ctx.instructions = SKILL_LISTING.format(description=_skill_description())
    started = datetime.now(UTC)
    clock = time.monotonic()
    final, error = "", None
    try:
        final = asyncio.run(asyncio.wait_for(run_agent(ctx), common.TIMEOUT))
    except Exception as exc:  # noqa: BLE001 - a failed run is kept, never replaced; its error is evidence.
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    wall = round(time.monotonic() - clock, 2)
    measured = [c for c in CALLS if c["input"] is not None]
    per_call = [c["input"] for c in measured]
    record = {
        "agent": agent,
        "kind": "framework",
        "version": " ".join(f"{p}=={importlib.metadata.version(p)}" for p in packages),
        "model": MODEL,
        "model_versions": sorted({c["model_version"] for c in CALLS if c["model_version"]}),
        "effort": "low",
        "condition": condition,
        "task": task,
        "rep": int(rep),
        "started_utc": started.isoformat(timespec="seconds"),
        "wall_seconds": wall,
        "error": error,
        "input": sum(per_call),
        "cache_read": sum(c["cache_read"] or 0 for c in measured),
        "output": sum(c["output"] or 0 for c in measured),
        "reasoning": sum(c["reasoning"] or 0 for c in measured),
        "model_calls": len(CALLS),
        "first_call_input": per_call[0] if per_call else None,
        "per_call_input": per_call,
        "per_call_declared_functions": [c["declared_functions"] for c in CALLS],
        "retries": sum(c["retries"] for c in CALLS),
        "commands": ctx.commands,
        "final": final if isinstance(final, str) else json.dumps(final),
    }
    (run / "stdout.jsonl").write_text("\n".join(ctx.transcript))
    (run / "log" / "first-request-tools.json").write_text(json.dumps(FIRST_TOOLS, indent=1, sort_keys=True) + "\n")
    common.finish(run, record, "\n".join(ctx.transcript))
    # Framework MCP clients can leave the server's process group behind on cancellation.
    subprocess.run(["pkill", "-f", str(run / "log" / "gate.jsonl")], check=False)
