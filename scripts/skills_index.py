# /// script
# requires-python = ">=3.13"
# dependencies = ["tiktoken==0.14.0", "pyyaml==6.0.3"]
# ///
# Counts a CLI-first skill catalogue with the same tokenizer and compact JSON
# serialization as the MCP declarations, read from a pinned commit rather than
# a working tree so local edits cannot change the observation.
import json
import subprocess
import sys
from pathlib import Path

import tiktoken
import yaml

REPOSITORY = "https://github.com/fmind/dot"
COMMIT = "4d65e1f591ce50f46bac407d2a27622abd0bffd1"
FOCUS = "gh"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "cli-skills.json"


def git(checkout: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"usage: skills_index.py <local clone of {REPOSITORY}>")
    checkout = Path(sys.argv[1])
    paths = sorted(
        path
        for path in git(checkout, "ls-tree", "-r", "--name-only", COMMIT, "skills").split()
        if path.count("/") == 2 and path.endswith("/SKILL.md")
    )
    encoding = tiktoken.get_encoding("o200k_base")

    def tokens(value: object) -> int:
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
        return len(encoding.encode(text))

    index, bodies = [], {}
    for path in paths:
        text = git(checkout, "show", f"{COMMIT}:{path}")
        front = yaml.safe_load(text.split("---", 2)[1])
        index.append({"name": front["name"], "description": front["description"]})
        bodies[front["name"]] = text
    focus = next(entry for entry in index if entry["name"] == FOCUS)
    result = {
        "source": f"{REPOSITORY}/tree/{COMMIT}/skills",
        "commit": COMMIT,
        "tokenizer": f"tiktoken {tiktoken.__version__} o200k_base",
        "serialization": "compact JSON, sorted keys, name and description only",
        "skills": len(index),
        "index_tokens": tokens(index),
        "focus_skill": FOCUS,
        "focus_index_tokens": tokens(focus),
        "focus_skill_file_tokens": tokens(bodies[FOCUS]),
        "scope": (
            "Startup discovery text and one loaded skill file."
            " Excludes host framing, CLI help, command output, and task execution."
        ),
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
