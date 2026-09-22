"""Recompute paired live-task results from complete native usage records."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def reported_count(usage: dict, field: str) -> int:
    """Retain valid reported counts; missing or invalid usage is not an estimate."""
    value = usage.get(field)
    return value if type(value) is int and value >= 0 else 0


def complete_usage(usage: dict) -> bool:
    """Require meaningful input and total counts before comparing a response."""
    required = ("prompt_token_count", "total_token_count")
    optional = ("candidates_token_count", "thoughts_token_count", "cached_content_token_count")
    return (
        all(type(usage.get(field)) is int and usage[field] > 0 for field in required)
        and all(type(usage[field]) is int and usage[field] >= 0 for field in optional if field in usage)
        and usage["total_token_count"] >= usage["prompt_token_count"]
        and usage.get("cached_content_token_count", 0) <= usage["prompt_token_count"]
    )


def summarize(trials: list[dict]) -> tuple[dict, list[dict]]:
    rows = []
    for trial in trials:
        turns = trial.get("turns", [])
        calls = trial.get("calls", [])
        usage = [turn.get("usage") if isinstance(turn.get("usage"), dict) else {} for turn in turns]
        rows.append(
            {
                "pair": trial["pair"],
                "mode": trial["mode"],
                "passed": trial.get("grade", {}).get("passed", False),
                "error": trial.get("error") or trial.get("reason"),
                "usage_complete": (
                    bool(turns)
                    and trial.get("error") is None
                    and "reason" not in trial
                    and all(complete_usage(item) for item in usage)
                ),
                "model_calls": len(turns),
                "input_tokens": sum(reported_count(item, "prompt_token_count") for item in usage),
                "output_tokens": sum(reported_count(item, "candidates_token_count") for item in usage),
                "thought_tokens": sum(reported_count(item, "thoughts_token_count") for item in usage),
                "cached_input_tokens": sum(reported_count(item, "cached_content_token_count") for item in usage),
                "total_tokens": sum(reported_count(item, "total_token_count") for item in usage),
                "peak_input_tokens": max((reported_count(item, "prompt_token_count") for item in usage), default=0),
                "discovery_calls": sum(c["name"] == "search_tools" for c in calls),
                "mcp_calls": sum(c["name"] != "search_tools" and c.get("ok", False) for c in calls),
                "wall_seconds": trial.get("wall_seconds"),
            }
        )
    summary = {}
    for mode in ["eager", "discovery"]:
        subset = [r for r in rows if r["mode"] == mode]
        completed = [r for r in subset if r["passed"] and r["usage_complete"]]
        summary[mode] = {
            "trials": len(subset),
            "passed": sum(r["passed"] for r in subset),
            "median_population": "successful trials with complete usage only",
            "median_sample_size": len(completed),
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
        if set(variants) == {"eager", "discovery"} and all(
            r["passed"] and r["usage_complete"] for r in variants.values()
        ):
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
        "Five repeats of one development task; not independent task coverage. Medians include successful trials only and are conditional on completion. CSV token sums are reported usage, not estimates for failed requests: zero with usage_complete=false means no usage returned, not free inference. Partial usage is retained but excluded from comparisons. Input includes cached tokens. Output and thought fields are reported separately without assuming an invoice."
    )
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    summary, rows = summarize(json.loads((args.directory / "trials.json").read_text()))
    (args.directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (args.directory / "trials.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
