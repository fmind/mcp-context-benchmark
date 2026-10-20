#!/usr/bin/env python3
"""Collect run records into one sanitized `records.jsonl` for publication.

Usage: collect.py <runs-dir> <results-dir>
Keeps each record's measurements, answer, GitHub calls, and shell commands; replaces the
run directory, home paths, and session identifiers with placeholders. Raw agent streams are
never copied. Every raw stream is re-audited for files read outside the run with the
current rule, and the record regraded, so every run is judged the same way. The frameworks'
first-request tool declarations (eager, hello, rep 1) are kept under `declarations/`.
"""

import json
import sys
from pathlib import Path

import common


def sanitize(text: str, run: Path, runs: Path) -> str:
    text = text.replace(str(run), "<run>").replace(str(runs), "<runs>").replace(str(common.REAL_HOME), "~")
    # Session and conversation identifiers appear in host paths; they are not evidence.
    return common.UUID.sub("<id>", text)


def main() -> None:
    runs, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    (output / "declarations").mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(runs.rglob("record.json")):
        run = path.parent
        record = json.loads(path.read_text())
        outside = common.outside_paths((run / "stdout.jsonl").read_text(errors="replace"), run)
        record["outside_paths"] = outside
        record["bypass_commands"] = common.bypasses(record.get("commands", []))
        record["grade"] = common.grade(
            record["task"],
            record["condition"],
            record["final"],
            record["github_calls"],
            record.get("commands", []),
            outside,
        )
        rows.append(json.loads(sanitize(json.dumps(record, ensure_ascii=False), run, runs)))
        tools = run / "log" / "first-request-tools.json"
        if record["kind"] == "framework" and (record["task"], record["condition"], record["rep"]) == (
            "hello",
            "eager",
            1,
        ):
            (output / "declarations" / f"{record['agent']}.json").write_text(tools.read_text())
    rows.sort(key=lambda r: (r["agent"], r["started_utc"]))
    (output / "records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    # Fail closed: nothing published may still name the home, the run directory, or a session.
    for path in [output / "records.jsonl", *(output / "declarations").glob("*.json")]:
        text = path.read_text()
        if str(common.REAL_HOME) in text or str(runs) in text or common.UUID.search(text):
            sys.exit(f"{path} still holds a local path or session identifier; fix sanitize() before publishing")
    print(len(rows), "records")


if __name__ == "__main__":
    main()
