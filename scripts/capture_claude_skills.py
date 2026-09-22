# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
"""Capture Claude Code's first request with MCP tools or agent skills, without inference.

Usage: python capture_claude_skills.py DOT_CLONE GITHUB_MCP_SERVER NEW_WORK_DIRECTORY

All variants run on the same installed CLI with identical flags, so each
addition is measured against a baseline from the same version. Skills come from
a pinned fmind/dot commit and are installed as user skills in an isolated
CLAUDE_CONFIG_DIR. The loopback endpoint returns HTTP 400 after capture.
"""

import io
import json
import os
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DOT_COMMIT = "4d65e1f591ce50f46bac407d2a27622abd0bffd1"
VARIANTS = ["baseline", "mcp-eager", "mcp-deferred", "skill-gh", "skills-all", "skills-all-unbudgeted"]
# Claude Code budgets skill metadata at 1% of the context window (8,000-character fallback)
# and drops descriptions on overflow; the last variant raises that budget to list them all.
UNBUDGETED_CHARS = "100000"
records: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        # Deliberately never persist headers, which would hold credentials in a real client.
        payload = json.loads(data)
        records.append(
            {"path": self.path, "body": {k: payload[k] for k in ("system", "messages", "tools") if k in payload}}
        )
        if "/messages" in self.path and "count_tokens" not in self.path:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                b'{"type":"error","error":{"type":"invalid_request_error",'
                b'"message":"Local benchmark captured request; no inference performed."}}'
            )
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")


def install_skills(dot: Path, target: Path, only: str | None) -> None:
    archive = subprocess.run(["git", "-C", str(dot), "archive", DOT_COMMIT, "skills"], check=True, capture_output=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        members = [m for m in tar.getmembers() if only is None or m.name.startswith(f"skills/{only}/")]
        tar.extractall(target, members=members, filter="data")


def skill_names(dot: Path) -> dict:
    """Read frontmatter names; hosts omit skills that disable model invocation from the listing."""
    paths = subprocess.run(
        ["git", "-C", str(dot), "ls-tree", "-r", "--name-only", DOT_COMMIT, "skills"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    names, hidden = [], []
    for path in sorted(p for p in paths if p.count("/") == 2 and p.endswith("/SKILL.md")):
        text = subprocess.run(
            ["git", "-C", str(dot), "show", f"{DOT_COMMIT}:{path}"], check=True, capture_output=True, text=True
        ).stdout
        front = text.split("---", 2)[1]
        name = next(line.split(":", 1)[1].strip().strip('"') for line in front.splitlines() if line.startswith("name:"))
        names.append(name)
        if "disable-model-invocation: true" in front:
            hidden.append(name)
    return {"installed_skills": names, "model_invocation_disabled": hidden}


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    dot, server_path, root = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    version = subprocess.run(["claude", "--version"], check=True, capture_output=True, text=True).stdout.strip()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for mode in VARIANTS:
            records.clear()
            work = root / mode
            config_dir = work / "config"
            config_dir.mkdir(parents=True)
            if mode.startswith("skill"):
                install_skills(dot, config_dir, "gh" if mode == "skill-gh" else None)
            mcp = {}
            if mode.startswith("mcp"):
                mcp = {
                    "github": {
                        "command": str(server_path),
                        "args": ["stdio", "--exclude-tools=delete_repository"],
                        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"},
                    }
                }
            config_path = work / "mcp.json"
            config_path.write_text(json.dumps({"mcpServers": mcp}))
            env = {
                "PATH": os.environ["PATH"],
                "LANG": "C.UTF-8",
                "HOME": str(work),
                "CLAUDE_CONFIG_DIR": str(config_dir),
                "ANTHROPIC_API_KEY": "dummy-local-capture-only",
                "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "ENABLE_TOOL_SEARCH": "true" if mode == "mcp-deferred" else "false",
                "DISABLE_TELEMETRY": "1",
                "DISABLE_ERROR_REPORTING": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            }
            if mode == "skills-all-unbudgeted":
                env["SLASH_COMMAND_TOOL_CHAR_BUDGET"] = UNBUDGETED_CHARS
            command = [
                "claude",
                "--print",
                "--setting-sources",
                "user",
                "--settings",
                '{"disableAllHooks":true}',
                "--system-prompt",
                "You are a benchmark assistant.",
                "--model",
                "claude-sonnet-4-6",
                "--tools",
                "ToolSearch,Skill",
                "--mcp-config",
                str(config_path),
                "--strict-mcp-config",
                "--no-session-persistence",
                "--max-turns",
                "1",
                "--output-format",
                "json",
                "Reply OK. Do not call tools.",
            ]
            try:
                result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=60)
                returncode = result.returncode
            except subprocess.TimeoutExpired:
                returncode = None
            first = next((r for r in records if "/messages" in r["path"] and "count_tokens" not in r["path"]), None)
            if first is None:
                raise RuntimeError(f"No model request captured for {mode}")
            body = json.loads(json.dumps(first["body"]).replace(str(work), "/benchmark"))
            (root / f"{mode}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
            print(mode, "exit", returncode, "tools", [t.get("name") for t in body.get("tools", [])][:6])
        (root / "provenance.json").write_text(
            json.dumps(
                {"claude": version, "dot_commit": DOT_COMMIT, "variants": VARIANTS, **skill_names(dot)}, indent=2
            )
            + "\n"
        )
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
