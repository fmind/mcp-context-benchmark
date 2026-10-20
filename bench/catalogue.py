# /// script
# requires-python = ">=3.13"
# dependencies = ["tiktoken==0.14.0"]
# ///
"""Measure what the GitHub MCP server offers before and after a call, without any model.

Usage: catalogue.py <output.json>
Requires GITHUB_MCP_SERVER (the verified v2.0.2 executable) and an authenticated `gh`.

1. Catalogue: `tools/list` for four configurations, negotiated as MCP 2025-11-25 (initialize)
   and as 2026-07-28 (stateless `_meta`), counted as declarations the way a client forwards
   them (name, description, input schema) and, separately, the output schemas.
2. Results: the three tools the tasks need, called read-only under both protocol versions,
   and the `gh` commands that return the same data, counted as raw text.

Counts use `o200k_base` over compact sorted JSON: a fixed ruler for comparing configurations,
not any provider's native count. Raw results are never stored, only sizes and digests.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import tiktoken

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ENCODING = tiktoken.get_encoding("o200k_base")
CONFIGS = {
    "all": ["stdio", "--toolsets=all"],
    "default": common.DEFAULT_ARGS,
    "read_only": ["stdio", "--read-only"],
    "allowlist": common.ROLE_ARGS,
}
MODERN = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "catalogue", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
CALLS = {
    "issue_read": {"method": "get", "owner": "github", "repo": "github-mcp-server", "issue_number": 2275},
    "get_file_contents": {
        "owner": "github",
        "repo": "github-mcp-server",
        "path": "pkg/github/tools.go",
        "ref": common.REF,
    },
    "get_release_by_tag": {"owner": "github", "repo": "github-mcp-server", "tag": "v1.12.2"},
}
GH = {
    "gh issue view (default)": ["issue", "view", "2275", "-R", "github/github-mcp-server"],
    "gh issue view --json title,state": ["issue", "view", "2275", "-R", "github/github-mcp-server", "--json", "title,state"],
    "gh api contents (default JSON, base64)": ["api", f"repos/github/github-mcp-server/contents/pkg/github/tools.go?ref={common.REF}"],
    "gh api contents (raw media type)": ["api", "-H", "Accept: application/vnd.github.raw", f"repos/github/github-mcp-server/contents/pkg/github/tools.go?ref={common.REF}"],
    "gh release view (default)": ["release", "view", "v1.12.2", "-R", "github/github-mcp-server"],
    "gh release view --json (6 fields)": ["release", "view", "v1.12.2", "-R", "github/github-mcp-server", "--json", "tagName,name,author,publishedAt,isPrerelease,isDraft"],
}  # fmt: skip


def tokens(value: object) -> int:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return len(ENCODING.encode(text))


class Server:
    """A minimal JSON-RPC client over the server's stdio, for either protocol version."""

    def __init__(self, args: list[str], modern: bool, token: str = "not-a-real-token-catalogue-only") -> None:
        self.modern = modern
        self.next_id = 0
        self.proc = subprocess.Popen(
            [str(common.server_path()), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env={"GITHUB_PERSONAL_ACCESS_TOKEN": token, "PATH": "/usr/bin:/bin"},
        )  # fmt: skip
        if modern:
            self.instructions = None
        else:
            init = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": MODERN["io.modelcontextprotocol/clientInfo"],
                },
            )
            self.instructions = init.get("instructions")
            self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        if self.modern:
            params = params | {"_meta": MODERN}
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            message = json.loads(line)
            if message.get("id") == self.next_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]
        raise RuntimeError(f"{method}: server closed")

    def tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += result.get("tools", [])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=10)


def catalogue() -> list[dict]:
    rows = []
    for config, args in CONFIGS.items():
        for modern in (False, True):
            server = Server(args, modern)
            tools = server.tools()
            server.close()
            declarations = [
                {"name": t["name"], "description": t.get("description", ""), "parameters": t["inputSchema"]}
                for t in tools
            ]
            rows.append(
                {
                    "config": config,
                    "protocol": "2026-07-28" if modern else "2025-11-25",
                    "tools": len(tools),
                    "declaration_tokens": tokens(declarations),
                    "output_schema_tools": sum("outputSchema" in t for t in tools),
                    "output_schema_tokens": sum(tokens(t["outputSchema"]) for t in tools if "outputSchema" in t),
                    "full_record_tokens": tokens(tools),
                    "instructions_tokens": tokens(server.instructions) if server.instructions else None,
                    "names_sha256": hashlib.sha256(json.dumps(sorted(t["name"] for t in tools)).encode()).hexdigest(),
                }
            )
    return rows


def size(text: str) -> dict:
    return {
        "chars": len(text),
        "tokens": tokens(text) if text else 0,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def results(token: str) -> list[dict]:
    rows = []
    for modern in (False, True):
        server = Server(common.DEFAULT_ARGS, modern, token)
        for name, arguments in CALLS.items():
            result = server.request("tools/call", {"name": name, "arguments": arguments})
            text = "".join(
                item.get("text", "") or (item.get("resource") or {}).get("text", "")
                for item in result.get("content", [])
                if isinstance(item, dict)
            )
            structured = result.get("structuredContent")
            rows.append(
                {
                    "interface": "mcp",
                    "protocol": "2026-07-28" if modern else "2025-11-25",
                    "call": name,
                    "content": size(text),
                    "structured": size(json.dumps(structured, sort_keys=True, ensure_ascii=False))
                    if structured
                    else None,
                    "structured_keys": sorted(structured) if isinstance(structured, dict) else None,
                }
            )
        server.close()
    for label, argv in GH.items():
        out = subprocess.run([common.real_gh(), *argv], capture_output=True, text=True, check=True).stdout
        rows.append({"interface": "cli", "call": label, "argv": argv, "content": size(out)})
    return rows


def main() -> None:
    output = Path(sys.argv[1])
    token = subprocess.run(
        [common.real_gh(), "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()
    version = subprocess.run(
        [str(common.server_path()), "--version"], capture_output=True, text=True, check=True
    ).stdout
    data = {
        "server": {
            "version": common.SERVER_VERSION,
            "build": version.strip().splitlines(),
            "binary_sha256": hashlib.sha256(common.server_path().read_bytes()).hexdigest(),
        },
        "tokenizer": f"tiktoken {tiktoken.__version__} / o200k_base",
        "catalogue": catalogue(),
        "results": results(token),
    }
    del token
    output.write_text(json.dumps(data, indent=2) + "\n")
    for row in data["catalogue"]:
        print(row["config"], row["protocol"], row["tools"], row["declaration_tokens"], row["output_schema_tokens"])
    for row in data["results"]:
        print(
            row["interface"],
            row.get("protocol", ""),
            row["call"],
            row["content"]["tokens"],
            (row.get("structured") or {}).get("tokens"),
        )


if __name__ == "__main__":
    main()
