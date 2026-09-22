# ruff: noqa: T201, S603
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import hashlib
import json
import os
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "codex-payloads"
OUT.mkdir(exist_ok=False)
records = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        # Retain only tool definitions; user-level instructions are out of scope.
        records.append({"path": self.path, "model": data.get("model"), "tools": data.get("tools", [])})
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"error":{"message":"Local benchmark captured request; no inference performed.","type":"invalid_request_error"}}'
        )


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
# This public release-derived fixture is a new control, not the missing historical cache.
fixture = ROOT / "codex-model.json"
model = json.loads(fixture.read_text())["models"][0]
if model["slug"] != "gpt-5.5":
    raise ValueError("The controlled capture requires the gpt-5.5 fixture")
executable = shutil.which("codex")
if executable is None:
    raise RuntimeError("Install Codex CLI 0.154.0 on PATH")
version = subprocess.check_output([executable, "--version"], text=True).strip()
if version != "codex-cli 0.154.0":
    raise ValueError("Install Codex CLI 0.154.0 for this controlled capture")
(OUT / "provenance.json").write_text(
    json.dumps(
        {
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "cli_version": version,
            "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fixture_source": "https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/models-manager/models.json",
            "configuration": "isolated CODEX_HOME and XDG_CONFIG_HOME per variant",
            "historical_configuration": False,
        },
        indent=2,
    )
    + "\n"
)
try:
    for mode in ["baseline", "eager", "deferred"]:
        records.clear()
        work = ROOT / f"codex-{mode}"
        work.mkdir(exist_ok=True)
        (work / "config").mkdir(exist_ok=True)
        model["supports_search_tool"] = mode != "eager"
        catalog = work / "models.json"
        catalog.write_text(json.dumps({"models": [model]}))
        overrides = {
            "model_provider": '"capture"',
            "model_providers.capture": '{name="Capture",base_url="http://127.0.0.1:'
            + str(server.server_port)
            + '/v1",wire_api="responses",requires_openai_auth=false,request_max_retries=0,stream_max_retries=0}',
            "model_catalog_json": json.dumps(str(catalog)),
            "web_search": '"disabled"',
            "features.apps": "false",
            "features.plugins": "false",
            "features.hooks": "false",
            "features.memories": "false",
            "features.multi_agent": "false",
            "features.multi_agent_v2": "false",
        }
        if mode != "baseline":
            overrides["mcp_servers.github"] = (
                "{command="
                + json.dumps(str(ROOT / "github/github-mcp-server"))
                + ',args=["stdio", "--exclude-tools=delete_repository"],env={GITHUB_PERSONAL_ACCESS_TOKEN="not-a-real-token-catalogue-only"}}'
            )
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            "gpt-5.5",
            "--json",
        ]
        for key, value in overrides.items():
            command.extend(["-c", f"{key}={value}"])
        command.append("Reply OK. Do not call tools.")
        try:
            result = subprocess.run(
                command,
                cwd=work,
                env={
                    "PATH": os.environ["PATH"],
                    "LANG": "C.UTF-8",
                    "CODEX_HOME": str(work / "config"),
                    "XDG_CONFIG_HOME": str(work / "xdg-config"),
                },
                capture_output=True,
                text=True,
                timeout=45,
            )
            # No prompt text or session history persisted in the evidence.
            (OUT / f"{mode}-process.json").write_text(
                json.dumps({"returncode": result.returncode, "stderr": result.stderr}, indent=2)
            )
        except subprocess.TimeoutExpired:
            print(mode, "timeout")
        (OUT / f"{mode}.json").write_text(json.dumps(records, indent=2))
        if not records:
            raise RuntimeError(f"No captured model request for {mode}; do not report a zero-token result")
        print(mode, "requests", len(records), [(r["path"], len(r["tools"])) for r in records])
finally:
    server.shutdown()
    server.server_close()
