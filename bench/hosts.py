#!/usr/bin/env python3
"""Run one GitHub task through a coding harness and record its native usage.

Each run gets a fresh workspace, a fresh harness home where the harness allows it, and a
read-only path to GitHub: MCP conditions reach the GitHub MCP server through `gate.py`,
and the CLI condition reaches the authenticated `gh` through `gh_shim.py`. Model tokens
come from each harness's own usage report. Raw output stays in the run directory.

Usage: hosts.py <out-dir> <claude|codex|agy> <condition> <task> <rep>
Credentials are read from the user's existing logins at run time and never written to the
record. The Codex home receives a copy of its login file, deleted when the run ends.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import common

MODELS = {
    "claude": ("claude-sonnet-5-5", "low"),
    "codex": ("gpt-6-luna", "low"),
    "agy": ("gemini-3.8-flash-low", "low"),
}
# default leaves the harness untouched; eager disables deferral where a harness exposes the knob.
SUPPORTED = {
    "claude": ("none", "default", "eager", "allowlist", "cli"),
    "codex": ("none", "default", "eager", "allowlist", "cli"),
    "agy": ("none", "default", "allowlist", "cli"),
}


def claude(run: Path, work: Path, condition: str, text: str, env: dict) -> tuple[list[str], dict]:
    model, effort = MODELS["claude"]
    config = run / "home" / ".claude"
    config.mkdir(parents=True)
    credentials = json.loads((common.REAL_HOME / ".claude" / ".credentials.json").read_text())
    env |= {
        "CLAUDE_CONFIG_DIR": str(config),
        "CLAUDE_CODE_OAUTH_TOKEN": credentials["claudeAiOauth"]["accessToken"],
        "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if condition == "eager":
        env["ENABLE_TOOL_SEARCH"] = "false"
    command = common.server_command(condition, run / "log" / "gate.jsonl")
    servers = {"github": {"command": command[0], "args": command[1:]}} if command else {}
    (run / "mcp.json").write_text(json.dumps({"mcpServers": servers}))
    if condition == "cli":
        common.install_skill(work / ".claude" / "skills")
    argv = [
        "claude", "-p", text,
        "--model", model,
        "--effort", effort,
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--mcp-config", str(run / "mcp.json"),
        "--permission-mode", "dontAsk",
        "--allowedTools", "Bash,Read,Grep,Glob,Skill,mcp__github",
        "--disallowedTools", "WebFetch,WebSearch",
        "--no-session-persistence",
    ]  # fmt: skip
    return argv, env


def codex(run: Path, work: Path, condition: str, text: str, env: dict) -> tuple[list[str], dict]:
    model, effort = MODELS["codex"]
    home = run / "home"
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True)
    shutil.copyfile(common.REAL_HOME / ".codex" / "auth.json", codex_home / "auth.json")
    (codex_home / "auth.json").chmod(0o600)
    cache = json.loads((common.REAL_HOME / ".codex" / "models_cache.json").read_text())
    entry = next(m for m in cache["models"] if m["slug"] == model)
    # The only difference between eager and default Codex is the model's search capability.
    entry = entry | {"supports_search_tool": condition != "eager"}
    (run / "models.json").write_text(json.dumps({"models": [entry]}))
    config = [
        f'model = "{model}"',
        f'model_reasoning_effort = "{effort}"',
        f"model_catalog_json = {json.dumps(str(run / 'models.json'))}",
        'approval_policy = "never"',
        'sandbox_mode = "workspace-write"',
        'web_search = "disabled"',
        # Codex's default sandbox has no network; only the CLI condition needs it for gh.
        "[sandbox_workspace_write]",
        f"network_access = {'true' if condition == 'cli' else 'false'}",
        f"writable_roots = [{json.dumps(str(run / 'log'))}]",
        "[features]",
        *(f"{name} = false" for name in ("apps", "plugins", "hooks", "memories", "multi_agent", "multi_agent_v2")),
    ]
    command = common.server_command(condition, run / "log" / "gate.jsonl")
    if command:
        config += [
            "[mcp_servers.github]",
            f"command = {json.dumps(command[0])}",
            f"args = {json.dumps(command[1:])}",
            "startup_timeout_sec = 60",
            "tool_timeout_sec = 120",
            'default_tools_approval_mode = "approve"',
        ]
    (codex_home / "config.toml").write_text("\n".join(config) + "\n")
    if condition == "cli":
        common.install_skill(work / ".agents" / "skills")
    # Codex runs `bash -lc`; a login shell would otherwise reset PATH and drop the shim.
    for profile in (".profile", ".bash_profile"):
        (home / profile).write_text(f"export PATH={json.dumps(env['PATH'])}\n")
    env |= {"HOME": str(home), "CODEX_HOME": str(codex_home), "XDG_CONFIG_HOME": str(home / ".config")}
    argv = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", str(work), text]
    return argv, env


def agy(run: Path, work: Path, condition: str, text: str, env: dict) -> tuple[list[str], dict]:
    model, effort = MODELS["agy"]
    command = common.server_command(condition, run / "log" / "gate.jsonl")
    servers = {"github": {"command": command[0], "args": command[1:]}} if command else {}
    (work / ".agents").mkdir(parents=True, exist_ok=True)
    (work / ".agents" / "mcp_config.json").write_text(json.dumps({"mcpServers": servers}))
    if condition == "cli":
        common.install_skill(work / ".agents" / "skills")
    argv = [
        "agy", "--new-project",
        "--model", model,
        "--effort", effort,
        "--dangerously-skip-permissions",
        "--print-timeout", f"{common.TIMEOUT - 20}s",
        "--output-format", "stream-json",
        "--print", text,
    ]  # fmt: skip
    return argv, env


def usage_claude(events: list[dict]) -> dict:
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    calls: dict[str, dict] = {}
    tools: list[str] = []
    commands: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message") or {}
        calls[message.get("id", str(len(calls)))] = message.get("usage") or {}
        uses = [b for b in message.get("content", []) if b.get("type") == "tool_use"]
        tools += [b.get("name") for b in uses]
        commands += [str((b.get("input") or {}).get("command", "")) for b in uses if b.get("name") == "Bash"]
    per_call = [
        u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        for u in calls.values()
    ]
    models = {
        name: {k: v for k, v in data.items() if isinstance(v, int | float)}
        for name, data in (result.get("modelUsage") or {}).items()
    }
    main = next((m for m in models if "sonnet" in m), None)
    u = models.get(main, {}) if main else {}
    return {
        "final": result.get("result", ""),
        "model": main,
        "input": u.get("inputTokens", 0) + u.get("cacheReadInputTokens", 0) + u.get("cacheCreationInputTokens", 0),
        "cache_read": u.get("cacheReadInputTokens"),
        "cache_write": u.get("cacheCreationInputTokens"),
        "output": u.get("outputTokens"),
        "model_calls": len(per_call),
        "first_call_input": per_call[0] if per_call else None,
        "per_call_input": per_call,
        "cost_usd_reported": result.get("total_cost_usd"),
        "other_models": {k: v for k, v in models.items() if k != main},
        "agent_tools": tools,
        "commands": commands,
    }


def usage_codex(events: list[dict], run: Path) -> dict:
    final, tools, commands, totals = "", [], [], {}
    for event in events:
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            final = item.get("text", "")
        if event.get("type") == "item.completed" and item.get("type") not in {"agent_message", "reasoning"}:
            tools.append(item.get("type") + (":" + str(item.get("tool")) if item.get("tool") else ""))
            if item.get("type") == "command_execution":
                commands.append(str(item.get("command", "")))
        if event.get("type") == "turn.completed":
            totals = event.get("usage") or {}
    per_call = []
    for rollout in sorted((run / "home" / ".codex" / "sessions").rglob("rollout-*.jsonl")):
        for row in common.read_jsonl(rollout):
            payload = row.get("payload") or {}
            if payload.get("type") == "token_count" and (payload.get("info") or {}).get("last_token_usage"):
                per_call.append(payload["info"]["last_token_usage"].get("input_tokens", 0))
    return {
        "final": final,
        "model": MODELS["codex"][0],
        "input": totals.get("input_tokens", 0),
        "cache_read": totals.get("cached_input_tokens"),
        "output": totals.get("output_tokens"),
        "reasoning": totals.get("reasoning_output_tokens"),
        "model_calls": len(per_call),
        "first_call_input": per_call[0] if per_call else None,
        "per_call_input": per_call,
        "agent_tools": tools,
        "commands": commands,
    }


def usage_agy(events: list[dict]) -> dict:
    result = next((e["result"] for e in reversed(events) if e.get("event") == "result"), {})
    u = result.get("usage") or {}
    steps = [e["step_update"] for e in events if e.get("event") == "step_update"]
    per_call = [
        s["usage"].get("input_tokens", 0) + s["usage"].get("cache_read_tokens", 0) for s in steps if s.get("usage")
    ]
    done = [s for s in steps if s.get("state") == "DONE" and s.get("step_type") == "tool"]
    commands = [
        str(((s.get("tool_info") or {}).get("parameters") or {}).get("CommandLine", ""))
        for s in done
        if s.get("tool_name") == "run_command"
    ]
    return {
        "final": result.get("response") or "",
        "model": MODELS["agy"][0],
        "input": u.get("input_tokens", 0) + u.get("cache_read_tokens", 0),
        "cache_read": u.get("cache_read_tokens"),
        "output": u.get("output_tokens"),
        "reasoning": u.get("thinking_tokens"),
        "model_calls": len(per_call),
        "first_call_input": per_call[0] if per_call else None,
        "per_call_input": per_call,
        "agent_tools": [s.get("tool_name") for s in done],
        "commands": commands,
    }


def events_of(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def main() -> None:
    out, agent, condition, task, rep = sys.argv[1:]
    if agent not in MODELS or condition not in SUPPORTED[agent] or task not in common.TASKS:
        sys.exit("invalid harness, condition, or task")
    run, work = common.prepare(out, agent, condition, task, rep)
    text = common.prompt(task, condition)
    env = {
        "PATH": f"{run / 'bin'}:{os.environ['PATH']}",
        "HOME": str(common.REAL_HOME),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
        "NO_COLOR": "1",
    }
    for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "USER"):
        if key in os.environ:
            env[key] = os.environ[key]
    argv, env = {"claude": claude, "codex": codex, "agy": agy}[agent](run, work, condition, text, env)
    started = datetime.now(UTC)
    clock = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=work, env=env, capture_output=True, text=True, timeout=common.TIMEOUT, check=False,
            stdin=subprocess.DEVNULL,
        )  # fmt: skip
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr, code = "timeout", None
    finally:
        # Delete the copied credentials as soon as the harness exits.
        (run / "home" / ".codex" / "auth.json").unlink(missing_ok=True)
    wall = round(time.monotonic() - clock, 2)
    (run / "stdout.jsonl").write_text(stdout)
    (run / "stderr.txt").write_text(stderr)
    events = events_of(stdout)
    usage = {"claude": lambda: usage_claude(events), "codex": lambda: usage_codex(events, run), "agy": lambda: usage_agy(events)}[agent]()  # fmt: skip
    record = {
        "agent": agent,
        "kind": "harness",
        "version": subprocess.run([agent, "--version"], capture_output=True, text=True, check=False).stdout.strip(),
        "effort": MODELS[agent][1],
        "condition": condition,
        "task": task,
        "rep": int(rep),
        "started_utc": started.isoformat(timespec="seconds"),
        "wall_seconds": wall,
        "returncode": code,
        **usage,
    }
    common.finish(run, record, stdout)


if __name__ == "__main__":
    main()
