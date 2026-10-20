#!/usr/bin/env python3
"""Run the declared schedule for one agent, resuming after completed runs.

Usage: study.py <out-dir> <agent>
Agents: claude, codex, agy (harnesses, via hosts.py) and langgraph, adk, pydantic
(frameworks, via `uv run --script <agent>_agent.py`). Conditions rotate within each
repetition so that no condition always runs first. A run whose directory exists is skipped:
a failed run is kept, never replaced, even one that crashed before writing its record.
"""

import subprocess
import sys
from pathlib import Path

from hosts import SUPPORTED

HERE = Path(__file__).resolve().parent
ORDER = ("none", "default", "eager", "search", "allowlist", "cli")
REPS = {"hello": 2, "issue": 5, "release": 5}
CONDITIONS = SUPPORTED | {
    "langgraph": ("none", "eager", "search", "allowlist", "cli"),
    "adk": ("none", "eager", "allowlist", "cli"),
    "pydantic": ("none", "eager", "search", "allowlist", "cli"),
}


def schedule(agent: str) -> list[tuple[str, str, int]]:
    runs = []
    for rep in range(1, max(REPS.values()) + 1):
        for task, count in REPS.items():
            if rep > count:
                continue
            conditions = [c for c in ORDER if c in CONDITIONS[agent] and (task == "hello" or c != "none")]
            shift = (rep - 1) % len(conditions)
            runs += [(task, c, rep) for c in conditions[shift:] + conditions[:shift]]
    return runs


def command(agent: str, out: str) -> list[str]:
    if agent in SUPPORTED:
        return [sys.executable, str(HERE / "hosts.py"), out, agent]
    return ["uv", "run", "--quiet", "--script", str(HERE / f"{agent}_agent.py"), out]


def main() -> None:
    out, agent = sys.argv[1:]
    if agent not in CONDITIONS:
        sys.exit(f"unknown agent; choose from {', '.join(CONDITIONS)}")
    for task, condition, rep in schedule(agent):
        run = Path(out) / agent / task / condition / f"rep{rep}"
        if run.exists():
            if not (run / "record.json").exists():
                print(f"kept incomplete run without a record: {run}", file=sys.stderr)
            continue
        subprocess.run([*command(agent, out), condition, task, str(rep)], check=False)


if __name__ == "__main__":
    main()
