# ruff: noqa: T201, S603
# Research instrumentation: progress output, fixed argv, and adapter-boundary inspection.
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "agy-results"
OUT.mkdir(exist_ok=True)
work = ROOT / "agy-work"
(work / ".agents").mkdir(parents=True, exist_ok=True)
for index, mode in enumerate(["baseline", "default", "all", "focused", "default", "baseline"]):
    servers = (
        {}
        if mode == "baseline"
        else {
            "github": {
                "command": str(ROOT / "github/github-mcp-server"),
                "args": [
                    "stdio",
                    "--exclude-tools=delete_repository",
                    "--log-file",
                    str(OUT / f"{index}-{mode}-mcp.log"),
                    "--enable-command-logging",
                    *(
                        ["--toolsets=all"]
                        if mode == "all"
                        else ["--toolsets=", "--tools=get_file_contents,search_code,issue_read"]
                        if mode == "focused"
                        else []
                    ),
                ],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "not-a-real-token-catalogue-only"},
            }
        }
    )
    (work / ".agents/mcp_config.json").write_text(json.dumps({"mcpServers": servers}))
    command = [
        "agy",
        "--new-project",
        "--model",
        "gemini-3.8-flash-high",
        "--effort",
        "high",
        "--mode",
        "plan",
        "--print-timeout",
        "45s",
        "--output-format",
        "json",
        "--print",
        "Respond with exactly OK. Do not use any tools, read any files, or perform any other action.",
    ]
    try:
        result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=55)
        (OUT / f"{index}-{mode}.json").write_text(
            json.dumps(
                {"mode": mode, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
                indent=2,
            )
        )
        print(index, mode, result.returncode, flush=True)
    except subprocess.TimeoutExpired:
        print(index, mode, "timeout", flush=True)
        break
