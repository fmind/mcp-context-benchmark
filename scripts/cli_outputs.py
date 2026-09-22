# /// script
# requires-python = ">=3.13"
# dependencies = ["tiktoken==0.14.0", "mcp==2.2.0"]
# ///
"""Count what a CLI and the GitHub MCP server return for the same read-only task data.

Usage: uv run --script scripts/cli_outputs.py GITHUB_MCP_SERVER

Reads public GitHub issue #2275 and the pinned tools.go source through `gh` and
through GitHub MCP v1.12.2, using the authenticated `gh` account for both. Only
byte sizes, SHA-256 digests, and o200k_base counts are retained: user-authored
issue text and source files are not redistributed. The issue is live, so later
runs can differ; the file reads are pinned to one commit.
"""

import asyncio
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import tiktoken
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = "github/github-mcp-server"
ISSUE = 2275
REF = "85598ba6e1256f7ebf4867b95d63b833c4549264"
SOURCE = "pkg/github/tools.go"
CONTENTS = f"repos/{REPO}/contents/{SOURCE}?ref={REF}"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "cli-outputs.json"
ENCODING = tiktoken.get_encoding("o200k_base")

COMMANDS = {
    "help:gh": ["--help"],
    "help:gh issue view": ["issue", "view", "--help"],
    "help:gh api": ["api", "--help"],
    "issue:default": ["issue", "view", str(ISSUE), "-R", REPO],
    "issue:comments": ["issue", "view", str(ISSUE), "-R", REPO, "--comments"],
    "issue:json-with-body": ["issue", "view", str(ISSUE), "-R", REPO, "--json", "number,title,state,url,body"],
    "issue:json-no-body": ["issue", "view", str(ISSUE), "-R", REPO, "--json", "number,title,state,url"],
    "file:api-default": ["api", CONTENTS],
    "file:api-raw": ["api", "-H", "Accept: application/vnd.github.raw", CONTENTS],
}


def measure(text: str) -> dict:
    data = text.encode()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "tokens": len(ENCODING.encode(text))}


def result_text(result: dict) -> str:
    """Join the text an MCP client would forward: text items and embedded resource text."""
    parts = []
    for item in result["content"]:
        if item["type"] == "text":
            parts.append(item["text"])
        elif item["type"] == "resource" and "text" in item["resource"]:
            parts.append(item["resource"]["text"])
    return "\n".join(parts)


async def mcp_outputs(server: Path, token: str) -> dict:
    params = StdioServerParameters(
        command=str(server),
        args=["stdio", "--exclude-tools=delete_repository"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
    )
    calls = {
        "mcp:issue_read": (
            "issue_read",
            {"owner": "github", "repo": "github-mcp-server", "method": "get", "issue_number": ISSUE},
        ),
        "mcp:get_file_contents": (
            "get_file_contents",
            {"owner": "github", "repo": "github-mcp-server", "path": SOURCE, "ref": REF},
        ),
    }
    outputs = {}
    async with stdio_client(params) as (read_stream, write_stream), ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        for label, (name, arguments) in calls.items():
            result = (await session.call_tool(name, arguments)).model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            if result.get("isError"):
                raise RuntimeError(f"{label} failed")
            outputs[label] = {"tool": name, "arguments": arguments, **measure(result_text(result))}
    return outputs


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    gh = shutil.which("gh")
    if gh is None:
        sys.exit("Install and authenticate gh")
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GH_PAGER": "", "NO_COLOR": "1", "GH_NO_UPDATE_NOTIFIER": "1"}
    outputs = {}
    for label, args in COMMANDS.items():
        stdout = subprocess.run([gh, *args], check=True, capture_output=True, text=True, env=env).stdout
        outputs[label] = {"command": ["gh", *args], **measure(stdout)}
    # The token reaches only the server's environment; it is never printed or retained.
    token = subprocess.run(
        [gh, "auth", "token", "--hostname", "github.com"], check=True, capture_output=True, text=True
    )
    outputs.update(asyncio.run(mcp_outputs(Path(sys.argv[1]).resolve(), token.stdout.strip())))
    version = subprocess.run([gh, "--version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    server = subprocess.run([sys.argv[1], "--version"], check=True, capture_output=True, text=True).stdout.split()
    result = {
        "captured_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gh": version,
        "github_mcp_server": server[server.index("Version:") + 1],
        "tokenizer": f"tiktoken {tiktoken.__version__} o200k_base, plain text",
        "scope": "Raw stdout or MCP result text; excludes host framing and any client-side projection or truncation.",
        "outputs": outputs,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    for label, row in outputs.items():
        print(f"{label:24} {row['tokens']:7} tokens {row['bytes']:7} bytes")


if __name__ == "__main__":
    main()
