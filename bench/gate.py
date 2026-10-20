#!/usr/bin/env python3
"""Read-only stdio gate between an agent and the GitHub MCP server.

The gate forwards discovery unchanged, so every agent sees the server's real catalogue,
but rejects any `tools/call` outside the read-only allowlist before it reaches GitHub.
It logs each call's name, arguments, outcome, and result size, never the result text, plus
the protocol version the client requested and how many listed tools carry an output schema.
The GitHub token comes from `gh auth token` at startup and exists only in the child env.

Usage: gate.py <log.jsonl> <gh> <gh-home> <github-mcp-server> [server args...]
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

READ_PREFIXES = ("get_", "list_", "search_")
READ_TOOLS = {"issue_read", "pull_request_read"}
META_VERSION = "io.modelcontextprotocol/protocolVersion"


def allowed(name: str) -> bool:
    return name in READ_TOOLS or name.startswith(READ_PREFIXES)


def main() -> None:
    log_path, gh, home, server, *args = sys.argv[1:]
    token = subprocess.run(
        [gh, "auth", "token"], capture_output=True, text=True, check=True, env={"HOME": home, "PATH": "/usr/bin:/bin"}
    ).stdout.strip()
    child = subprocess.Popen(
        [server, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "GITHUB_PERSONAL_ACCESS_TOKEN": token},
        text=True,
        bufsize=1,
    )
    del token
    log = Path(log_path).open("a", encoding="utf-8")  # noqa: SIM115 - open for the process lifetime
    lock = threading.Lock()
    pending: dict[object, dict] = {}

    def record(entry: dict) -> None:
        with lock:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
            log.flush()

    def reply(line: str) -> None:
        with lock:
            sys.stdout.write(line if line.endswith("\n") else line + "\n")
            sys.stdout.flush()

    def upstream() -> None:
        assert child.stdout is not None
        for line in child.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                reply(line)
                continue
            # Only a response (no method) answers a pending call; server requests reuse id space.
            is_response = isinstance(message, dict) and "method" not in message
            call = pending.pop(message.get("id"), None) if is_response else None
            if call is not None:
                result = message.get("result") or {}
                text = "".join(
                    item.get("text", "") or (item.get("resource") or {}).get("text", "")
                    for item in result.get("content", [])
                    if isinstance(item, dict)
                )
                call.update(
                    ok="error" not in message and not result.get("isError", False),
                    result_chars=len(text),
                    seconds=round(time.monotonic() - call.pop("started"), 3),
                )
                record(call)
            elif isinstance(message, dict) and message.get("id") is not None and "result" in message:
                tools = (message.get("result") or {}).get("tools")
                if isinstance(tools, list):
                    schemas = sum(isinstance(t, dict) and "outputSchema" in t for t in tools)
                    names = sorted(str(t.get("name")) for t in tools if isinstance(t, dict))
                    record(
                        {"event": "tools/list:result", "count": len(tools), "output_schemas": schemas, "names": names}
                    )
            reply(line)
        sys.stdout.close()

    threading.Thread(target=upstream, daemon=True).start()
    assert child.stdin is not None
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            child.stdin.write(line)
            child.stdin.flush()
            continue
        if not isinstance(message, dict):
            # MCP has no batches since 2025-06-18; refuse them rather than forward unchecked calls.
            record({"event": "batch", "ok": False, "blocked": True})
            error = {"code": -32600, "message": "Blocked by benchmark gate: batches are not supported."}
            reply(json.dumps({"jsonrpc": "2.0", "id": None, "error": error}))
            continue
        if message.get("method") == "tools/call":
            params = message.get("params") or {}
            name = str(params.get("name", ""))
            entry = {"event": "tools/call", "name": name, "arguments": params.get("arguments")}
            if not allowed(name):
                record({**entry, "ok": False, "blocked": True})
                reply(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": message.get("id"),
                            "result": {
                                "isError": True,
                                "content": [
                                    {"type": "text", "text": f"Blocked by benchmark gate: {name} is not read-only."}
                                ],
                            },
                        }
                    )
                )
                continue
            pending[message.get("id")] = {**entry, "started": time.monotonic()}
        elif message.get("method"):
            params = message.get("params") or {}
            # 2025 clients negotiate in initialize; 2026-07-28 clients stamp every request's _meta.
            version = params.get("protocolVersion") if message["method"] == "initialize" else None
            version = version or (params.get("_meta") or {}).get(META_VERSION)
            record({"event": message["method"], **({"protocol_version": version} if version else {})})
        child.stdin.write(line)
        child.stdin.flush()
    child.stdin.close()
    child.wait(timeout=10)


if __name__ == "__main__":
    main()
