# ruff: noqa: T201, S603
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "claude-payloads"
OUT.mkdir(exist_ok=True)


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
                b'{"type":"error","error":{"type":"invalid_request_error","message":"Local benchmark captured request; no inference performed."}}'
            )
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")


records = []
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    for mode in ["baseline", "eager", "deferred"]:
        records.clear()
        work = ROOT / f"claude-{mode}"
        work.mkdir(exist_ok=True)
        config = (
            {}
            if mode == "baseline"
            else {
                "github": {
                    "command": str(ROOT / "github/github-mcp-server"),
                    "args": ["stdio", "--exclude-tools=delete_repository"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"},
                }
            }
        )
        config_path = work / "mcp.json"
        config_path.write_text(json.dumps({"mcpServers": config}))
        env = {
            "PATH": os.environ["PATH"],
            "LANG": "C.UTF-8",
            "CLAUDE_CONFIG_DIR": str(work / "config"),
            "ANTHROPIC_API_KEY": "dummy-local-capture-only",
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "ENABLE_TOOL_SEARCH": "true" if mode == "deferred" else "false",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        command = [
            "claude",
            "--print",
            "--setting-sources",
            "",
            "--settings",
            '{"disableAllHooks":true}',
            "--system-prompt",
            "You are a benchmark assistant.",
            "--model",
            "claude-sonnet-4-6",
            "--tools",
            "ToolSearch",
            "--mcp-config",
            str(config_path),
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--max-turns",
            "1",
            "--output-format",
            "json",
            "Reply OK. Do not call tools.",
        ]
        try:
            result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=50)
            (OUT / f"{mode}-process.json").write_text(
                json.dumps(
                    {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2
                )
            )
        except subprocess.TimeoutExpired:
            print(mode, "timeout")
        (OUT / f"{mode}.json").write_text(json.dumps(records, indent=2))
        print(mode, "requests", len(records), [(r["path"], len(r["body"].get("tools", []))) for r in records])
finally:
    server.shutdown()
    server.server_close()
