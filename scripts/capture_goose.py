# ruff: noqa: T201, S603
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "goose-payloads"
OUT.mkdir(exist_ok=True)
records = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        records.append({"path": self.path, "body": {"tools": data.get("tools", [])}})
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"type":"error","error":{"type":"invalid_request_error","message":"Local benchmark captured request; no inference performed."}}'
        )


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    for mode in ["baseline", "eager", "code_mode"]:
        records.clear()
        work = ROOT / f"goose-{mode}"
        work.mkdir(exist_ok=True)
        env = {
            "PATH": os.environ["PATH"],
            "LANG": "C.UTF-8",
            "GOOSE_PROVIDER": "anthropic",
            "GOOSE_MODEL": "claude-sonnet-4-6",
            "ANTHROPIC_API_KEY": "dummy-local-capture-only",
            "ANTHROPIC_HOST": f"http://127.0.0.1:{server.server_port}",
            "XDG_CONFIG_HOME": str(work / "config"),
            "XDG_DATA_HOME": str(work / "data"),
            "GOOSE_TELEMETRY_ENABLED": "false",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only",
        }
        command = [
            str(ROOT / "goose-gnu/goose"),
            "run",
            "--no-profile",
            "--no-session",
            "--max-turns",
            "1",
            "--text",
            "Reply OK. Do not call tools.",
        ]
        if mode != "baseline":
            command += [
                "--with-extension",
                f"github:{ROOT}/github/github-mcp-server stdio --exclude-tools=delete_repository",
            ]
        env["GOOSE_DISABLE_SESSION_NAMING"] = "true"
        if mode == "code_mode":
            recipe = work / "capture.yaml"
            recipe.write_text(
                "version: 1.0.0\ntitle: Local schema capture\ndescription: Capture request without inference\ninstructions: Respond with OK.\nprompt: Reply OK. Do not call tools.\nextensions:\n  - type: platform\n    name: code_execution\n    description: Code Mode\n    available_tools: []\n  - type: stdio\n    name: github\n    cmd: "
                + str(ROOT / "github/github-mcp-server")
                + '\n    args: [stdio, "--exclude-tools=delete_repository"]\n    envs:\n      GITHUB_PERSONAL_ACCESS_TOKEN: not-a-real-token-catalogue-only\n    timeout: 30\n'
            )
            command.remove("--text")
            command.remove("Reply OK. Do not call tools.")
            command.remove("--no-profile")
            command.remove("--with-extension")
            command.remove(f"github:{ROOT}/github/github-mcp-server stdio --exclude-tools=delete_repository")
            command += ["--recipe", str(recipe)]
        try:
            result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=45)
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
