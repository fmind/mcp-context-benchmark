"""Extract shareable measurement fields from a fresh collection directory.

Usage: python normalize.py RAW_DIRECTORY NEW_DATA_DIRECTORY
Do not publish raw process logs or model catalogues.
"""

import argparse
import json
import re
from pathlib import Path


def load(path: Path) -> dict | list:
    """Read a raw JSON observation."""
    return json.loads(path.read_text())


def main() -> None:
    """Normalize fresh captures without overwriting the retained experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)

    def save(name: str, value: object) -> None:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    for mode in ["default", "all", "read_only", "focused"]:
        name = f"github-{mode}.json"
        save(name, load(args.raw / name))
    for path in (args.raw / "framework-payloads").glob("*.json"):
        if "error" in path.name or path.name in ["pydantic-eager.json", "pydantic-focused.json"]:
            continue
        payload = load(path)
        if path.name == "pydantic-deferred.json":
            for message in payload["messages"]:
                message.pop("conversation_id", None)
                message.pop("run_id", None)
        save(path.name, payload)
    for host in ["claude", "codex", "goose"]:
        for mode in ["baseline", "eager", "code_mode" if host == "goose" else "deferred"]:
            records = load(args.raw / f"{host}-payloads/{mode}.json")
            if not records:
                raise ValueError(f"Empty capture: {host}/{mode}")
            body = records[0].get("body", records[0])
            if host == "claude":
                body = {k: body[k] for k in ["system", "messages", "tools"] if k in body}
                body = json.loads(json.dumps(body).replace(str(args.raw / f"claude-{mode}"), "/benchmark"))
            else:
                body = {"tools": body.get("tools", [])}
            save(f"{host}-{mode}.json", body)
    # No fallback to stored usage: missing native probes remain unmeasured.
    if not (args.raw / "agy-results/0-baseline.json").is_file():
        return
    observations = []
    for index, mode in enumerate(["baseline", "default", "all", "focused", "default", "baseline"]):
        process = load(args.raw / f"agy-results/{index}-{mode}.json")
        response = json.loads(process["stdout"])
        row = {
            "index": index,
            "mode": mode,
            **{k: response[k] for k in ["status", "response", "duration_seconds", "num_turns", "usage"]},
        }
        methods, tools = [], []
        if mode != "baseline":
            for line in (args.raw / f"agy-results/{index}-{mode}-mcp.log").read_text().splitlines():
                match = re.search(r' data=(".*")$', line)
                if not match:
                    continue
                message = json.loads(json.loads(match[1]))
                if "method" in message:
                    methods.append(message["method"])
                if "result" in message and "tools" in message["result"]:
                    tools.extend(message["result"]["tools"])
            if not tools:
                raise ValueError(f"No tools discovered: Antigravity/{mode}")
        row.update(
            mcp_methods=methods,
            mcp_tools_count=len(tools),
            mcp_tool_names=sorted(t["name"] for t in tools),
            tools_call_count=methods.count("tools/call"),
        )
        observations.append(row)
    save("antigravity.json", observations)


if __name__ == "__main__":
    main()
