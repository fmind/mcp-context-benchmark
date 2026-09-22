# /// script
# requires-python = ">=3.13"
# dependencies = ["tiktoken==0.14.0"]
# ///
"""Recompute the CLI and skill comparison from retained, sanitized observations.

Reads the Claude Code skill captures, the skill index count, and the CLI/MCP
output counts, validates their controls, and writes cli-results.json. No
network, credentials, or inference are needed.
"""

import json
from pathlib import Path

import tiktoken

ROOT = Path(__file__).parent
CAPTURES = ROOT / "validation" / "claude-skills-2026-09-22"
ENCODING = tiktoken.get_encoding("o200k_base")


def tokens(value: object) -> int:
    """Count the same stable JSON representation as analyze.py."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return len(ENCODING.encode(text))


def require(condition: bool, message: str) -> None:
    """Reject invalid experimental controls."""
    if not condition:
        raise ValueError(message)


def listing(body: dict) -> list[str]:
    """Return the skill entries Claude Code listed in its first request."""
    blocks = [
        item["text"]
        for message in body["messages"]
        for item in message["content"]
        if "skills are available" in item.get("text", "")
    ]
    require(len(blocks) == 1, "Expected exactly one skill listing")
    return [line for line in blocks[0].splitlines() if line.startswith("- ")]


def main() -> None:
    """Validate controls and write the comparison."""
    provenance = json.loads((CAPTURES / "provenance.json").read_text())
    bodies = {mode: json.loads((CAPTURES / f"{mode}.json").read_text()) for mode in provenance["variants"]}
    expected = {t["name"] for t in json.loads((ROOT / "data" / "github-default.json").read_text())["tools"]}
    github = {
        mode: {
            t["name"].removeprefix("mcp__github__")
            for t in body.get("tools", [])
            if t["name"].startswith("mcp__github__")
        }
        for mode, body in bodies.items()
    }
    require(github["mcp-eager"] == expected, "Eager capture lacks the 45 default GitHub tools")
    require(all(not names for mode, names in github.items() if mode != "mcp-eager"), "Unexpected eager GitHub tools")
    require({t["name"] for t in bodies["mcp-deferred"]["tools"]} >= {"ToolSearch"}, "Tool search unavailable")
    entries = {mode: listing(body) for mode, body in bodies.items()}
    names = {mode: {line[2:].split(":", 1)[0] for line in lines} for mode, lines in entries.items()}
    require("gh" in names["skill-gh"] and "gh" not in names["baseline"], "gh skill control failed")
    visible = set(provenance["installed_skills"]) - set(provenance["model_invocation_disabled"])
    require(visible <= names["skills-all"], "A model-invocable fmind/dot skill is missing from the listing")
    require(not set(provenance["model_invocation_disabled"]) & names["skills-all"], "A hidden skill was listed")
    require(names["skills-all"] == names["skills-all-unbudgeted"], "Unbudgeted listing changed the skill set")
    baseline = tokens(bodies["baseline"])
    host = []
    for mode, body in bodies.items():
        host.append(
            {
                "variant": mode,
                "total": tokens(body),
                "addition": tokens(body) - baseline,
                "listed_skills": len(entries[mode]),
                "listed_without_description": sum(":" not in line for line in entries[mode]),
            }
        )
    outputs = json.loads((ROOT / "data" / "cli-outputs.json").read_text())
    result = {
        "claude": provenance["claude"],
        "dot_commit": provenance["dot_commit"],
        "host_scope": (
            "JSON system + messages + tools of the first request; additions subtract the same-version baseline"
        ),
        "installed_skills": len(provenance["installed_skills"]),
        "model_invocable_skills": len(visible),
        "skills_replacing_builtins": sorted(visible & names["baseline"]),
        "host": host,
        "skill_index": json.loads((ROOT / "data" / "cli-skills.json").read_text()),
        "outputs": {
            "captured_utc": outputs["captured_utc"],
            "gh": outputs["gh"],
            "github_mcp_server": outputs["github_mcp_server"],
            "tokens": {label: row["tokens"] for label, row in outputs["outputs"].items()},
        },
    }
    (ROOT / "cli-results.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in host:
        listed, bare = row["listed_skills"], row["listed_without_description"]
        print(f"{row['variant']:22} +{row['addition']:6}  listed {listed:3}  name-only {bare:3}")


if __name__ == "__main__":
    main()
