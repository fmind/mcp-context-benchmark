"""Analyze all declared study trials; never turn absent usage into a saving."""

import argparse
import json
from pathlib import Path
from statistics import median

from analyze_task import complete_usage, reported_count

MODES = ("eager", "fixed", "discovery")


def analyze(records: list[dict], cases: list[dict]) -> dict:
    expected = {(c["id"], b, m, p) for c in cases for b in range(3) for m in MODES for p in ("first", "repeat")}
    observed = [(r["case"], r["block"], r["mode"], r["phase"]) for r in records]
    if len(set(observed)) != len(observed) or set(observed) - expected:
        raise ValueError("Unexpected or duplicate trial identity")
    rows = []
    for record in records:
        usages = [turn.get("usage") or {} for turn in record.get("turns", [])]
        cached = [u.get("cached_content_token_count") for u in usages]
        # Omitted cache accounting stays unknown; do not label it an uncached observation.
        cache_known = bool(usages) and all(type(v) is int and v >= 0 for v in cached)
        rows.append(
            {
                **{k: record[k] for k in ("case", "block", "mode", "phase")},
                "passed": record.get("grade", {}).get("passed", False),
                "error": record.get("error") or record.get("reason"),
                "usage_complete": bool(usages)
                and all(complete_usage(u) for u in usages)
                and not record.get("error")
                and not record.get("reason"),
                "input_tokens": sum(reported_count(u, "prompt_token_count") for u in usages),
                "total_tokens": sum(reported_count(u, "total_token_count") for u in usages),
                "peak_input_tokens": max((reported_count(u, "prompt_token_count") for u in usages), default=0),
                "cached_input_tokens": sum(cached) if cache_known else None,
                "cache_observation": ("cache_hit" if any(cached) else "reported_zero") if cache_known else "unknown",
                "model_calls_with_response": len(usages),
                "discovery_calls": sum(c["name"] == "search_tools" for c in record.get("calls", [])),
                "blocked_calls": sum(bool(c.get("blocked")) for c in record.get("calls", [])),
                "wall_seconds_including_token_preflight": record.get("wall_seconds"),
            }
        )
    groups, comparisons = [], []
    for case in cases:
        for phase in ("first", "repeat"):
            for mode in MODES:
                selected = [r for r in rows if (r["case"], r["phase"], r["mode"]) == (case["id"], phase, mode)]
                complete = [r for r in selected if r["passed"] and r["usage_complete"]]
                groups.append(
                    {
                        "case": case["id"],
                        "phase": phase,
                        "mode": mode,
                        "planned": 3,
                        "recorded": len(selected),
                        "passed": sum(r["passed"] for r in selected),
                        "complete_successes": len(complete),
                        "median_input_successes_only": median(r["input_tokens"] for r in complete)
                        if complete
                        else None,
                    }
                )
            for block in range(3):
                variants = {
                    r["mode"]: r for r in rows if (r["case"], r["phase"], r["block"]) == (case["id"], phase, block)
                }
                if set(variants) == set(MODES) and all(r["passed"] and r["usage_complete"] for r in variants.values()):
                    comparisons.append(
                        {
                            "case": case["id"],
                            "phase": phase,
                            "block": block,
                            **{
                                f"{m}_input_reduction_percent": 100
                                * (1 - variants[m]["input_tokens"] / variants["eager"]["input_tokens"])
                                for m in ("fixed", "discovery")
                            },
                        }
                    )
    all_pass = set(observed) == expected and all(r["passed"] and r["usage_complete"] for r in rows)
    verdicts = {
        mode: "useful_for_these_cases"
        if all_pass and all(c[f"{mode}_input_reduction_percent"] > 0 for c in comparisons)
        else "inconclusive_or_mixed"
        for mode in ("fixed", "discovery")
    }
    return {
        "planned": len(expected),
        "recorded": len(records),
        "missing": len(expected - set(observed)),
        "verdicts": verdicts,
        "groups": groups,
        "complete_matched_triplets": comparisons,
        "rows": rows,
        "limits": "Three bounded tasks, three repeats per phase; not 54 independent tasks. First/repeat is request ordering, not controlled cache state. Missing cache fields are unknown. No latency or invoice advantage inferred.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    cases = json.loads((args.directory / "study-cases.json").read_text())["cases"]
    records = json.loads((args.directory / "trials.json").read_text())
    (args.directory / "summary.json").write_text(json.dumps(analyze(records, cases), indent=2) + "\n")


if __name__ == "__main__":
    main()
