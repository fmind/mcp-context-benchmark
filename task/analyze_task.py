"""Recompute paired live-task results from complete native usage records."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def summarize(trials: list[dict]) -> tuple[dict, list[dict]]:
    rows = []
    for trial in trials:
        turns = trial.get("turns", [])
        calls = trial.get("calls", [])
        rows.append(
            {
                "pair": trial["pair"],
                "mode": trial["mode"],
                "passed": trial.get("grade", {}).get("passed", False),
                "error": trial.get("error") or trial.get("reason"),
                "model_calls": len(turns),
                "input_tokens": sum(t["usage"].get("prompt_token_count", 0) for t in turns),
                "output_tokens": sum(t["usage"].get("candidates_token_count", 0) for t in turns),
                "thought_tokens": sum(t["usage"].get("thoughts_token_count", 0) for t in turns),
                "cached_input_tokens": sum(t["usage"].get("cached_content_token_count", 0) for t in turns),
                "total_tokens": sum(t["usage"].get("total_token_count", 0) for t in turns),
                "peak_input_tokens": max((t["usage"].get("prompt_token_count", 0) for t in turns), default=0),
                "discovery_calls": sum(c["name"] == "search_tools" for c in calls),
                "mcp_calls": sum(c["name"] != "search_tools" and c.get("ok", False) for c in calls),
                "wall_seconds": trial.get("wall_seconds"),
            }
        )
    summary = {}
    for mode in ["eager", "discovery"]:
        subset = [r for r in rows if r["mode"] == mode]
        completed = [r for r in subset if r["model_calls"] and r["wall_seconds"] is not None]
        summary[mode] = {
            "trials": len(subset),
            "passed": sum(r["passed"] for r in subset),
            **{
                f"median_{field}": median(r[field] for r in completed) if completed else None
                for field in [
                    "input_tokens",
                    "output_tokens",
                    "thought_tokens",
                    "cached_input_tokens",
                    "total_tokens",
                    "peak_input_tokens",
                    "model_calls",
                    "discovery_calls",
                    "mcp_calls",
                    "wall_seconds",
                ]
            },
        }
    paired = []
    for pair in range(5):
        variants = {r["mode"]: r for r in rows if r["pair"] == pair}
        if len(variants) == 2 and all(r["passed"] for r in variants.values()):
            a, b = variants["eager"], variants["discovery"]
            paired.append(
                {
                    "pair": pair,
                    "input_reduction_percent": 100 * (1 - b["input_tokens"] / a["input_tokens"]),
                    "total_reduction_percent": 100 * (1 - b["total_tokens"] / a["total_tokens"]),
                    "wall_change_seconds": b["wall_seconds"] - a["wall_seconds"],
                }
            )
    summary["paired"] = paired
    summary["verdict"] = (
        "useful_for_this_case"
        if len(paired) == 5 and all(r["input_reduction_percent"] > 0 for r in paired)
        else "inconclusive_or_mixed"
    )
    summary["interpretation"] = (
        "Five repeats of one development task; not independent task coverage. Input includes cached tokens. Output and thought fields are reported separately without assuming an invoice."
    )
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    summary, rows = summarize(json.loads((args.directory / "trials.json").read_text()))
    (args.directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (args.directory / "trials.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
