# /// script
# requires-python = ">=3.13"
# dependencies = ["matplotlib==3.11.2", "tiktoken==0.14.0"]
# ///
"""Summarize the study and draw its figures from retained data only.

Usage: analyze.py <results-dir>
Reads `records.jsonl`, `catalogue.json`, and `declarations/` and writes `summary.json`,
`summary.md`, and `figures/*.png`. Every attempted run counts toward pass rates. Token
medians use the passing runs, so that an early failure does not look cheap; `*_all` fields
use every run that reported usage, and a cell where nothing passed is drawn from those.
`input` is cumulative native input across all model calls, cache included.
"""

import json
import statistics
import sys
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import tiktoken
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "GoogleSans-Regular.ttf"
AGENTS = ("claude", "codex", "agy", "langgraph", "adk", "pydantic")
NAMES = {
    "claude": ("Claude Code", "Sonnet 5.5"),
    "codex": ("Codex CLI", "GPT-6-Luna"),
    "agy": ("Antigravity CLI", "Gemini 3.8 Flash"),
    "langgraph": ("LangGraph", "Gemini 3.8 Flash"),
    "adk": ("Google ADK", "Gemini 3.8 Flash"),
    "pydantic": ("PydanticAI", "Gemini 3.8 Flash"),
}
ORDER = ("none", "default", "eager", "search", "allowlist", "cli")
TASKS = ("hello", "issue", "release")
# Fixed categorical order, validated for adjacent-pair CVD separation; every bar is also labeled.
COLORS = {"eager": "#A50E0E", "default": "#174EA6", "search": "#E37400", "allowlist": "#4285F4", "cli": "#0D652D"}
LABELS = {
    "default": "Default MCP",
    "eager": "Eager MCP",
    "search": "Tool search",
    "allowlist": "3-tool allowlist",
    "cli": "gh + skill",
}
INK, MUTED, BASE = "#202124", "#595D62", "#DADCE0"
ENCODING = tiktoken.get_encoding("o200k_base")


def median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def label(agent: str, condition: str) -> str:
    # A framework's untouched default is eager loading.
    return (
        "Eager MCP (default)"
        if condition == "eager" and agent in {"langgraph", "adk", "pydantic"}
        else LABELS[condition]
    )


def summarize(records: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        groups.setdefault((record["agent"], record["task"], record["condition"]), []).append(record)
    rows = []
    for agent in AGENTS:
        for task in TASKS:
            for condition in ORDER:
                runs = groups.get((agent, task, condition))
                if not runs:
                    continue
                every = [r for r in runs if r.get("input")]
                passed = [r for r in every if r["grade"]["passed"]]
                measured = passed or every
                rows.append(
                    {
                        "agent": agent,
                        "kind": runs[0]["kind"],
                        "versions": sorted({r["version"] for r in runs}),
                        "model": runs[0].get("model"),
                        "task": task,
                        "condition": condition,
                        "runs": len(runs),
                        "passed": sum(r["grade"]["passed"] for r in runs),
                        "citation": sum(bool(r["grade"].get("citation")) for r in runs) if task == "issue" else None,
                        "errors": sorted(
                            {e for r in runs for e in r["grade"]["errors"]}
                            | {r["error"].split(":")[0] for r in runs if r.get("error")}
                        ),
                        "median_first_call_input": median([r.get("first_call_input") for r in measured]),
                        "measured_on": "passed" if passed else "all",
                        "median_input": median([r["input"] for r in measured]),
                        "median_input_all": median([r["input"] for r in every]),
                        "min_input": min((r["input"] for r in measured), default=None),
                        "max_input": max((r["input"] for r in measured), default=None),
                        "median_cache_read": median([r.get("cache_read") for r in measured]),
                        "median_output": median([r.get("output") for r in measured]),
                        "median_model_calls": median([r.get("model_calls") for r in measured]),
                        "median_github_calls": median([len(r["github_calls"]) for r in runs]),
                        "median_result_chars": median(
                            [
                                sum(c.get("result_chars") or c.get("stdout_chars") or 0 for c in r["github_calls"])
                                for r in runs
                            ]
                        ),
                        "median_wall_seconds": median([r["wall_seconds"] for r in runs]),
                        "median_cost_usd_reported": median([r.get("cost_usd_reported") for r in runs]),
                        "protocols": sorted({v for r in runs for v in r.get("mcp_protocol_versions", [])}),
                        "tools_listed": sorted({n for r in runs for n in r.get("mcp_tools_listed", [])}),
                    }
                )
    return rows


def table(rows: list[dict]) -> str:
    head = "| Agent | Task | Condition | Pass | First call | Median input | Range | Calls | Output | Wall s |"
    lines = [head, "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]

    def fmt(v: float | None) -> str:
        return "-" if v is None else f"{v:,.0f}"

    for s in rows:
        lines.append(
            f"| {s['agent']} | {s['task']} | {s['condition']} | {s['passed']}/{s['runs']} | "
            f"{fmt(s['median_first_call_input'])} | {fmt(s['median_input'])} | {fmt(s['min_input'])}-{fmt(s['max_input'])} | "
            f"{fmt(s['median_model_calls'])} | {fmt(s['median_output'])} | {s['median_wall_seconds']:.1f} |"
        )
    return "\n".join(lines) + "\n"


def declarations(folder: Path) -> dict:
    """Reference tokens of each framework's first request tool declarations (46 tools, eager)."""
    found = {}
    for path in sorted((folder / "declarations").glob("*.json")):
        tools = json.loads(path.read_text())
        text = json.dumps(tools, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        found[path.stem] = {"tools": len(tools), "reference_tokens": len(ENCODING.encode(text))}
    return found


def style() -> None:
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update(
        {"font.family": "Google Sans", "font.size": 12, "text.color": INK, "axes.labelcolor": INK,
         "xtick.color": MUTED, "ytick.color": INK, "axes.edgecolor": BASE}
    )  # fmt: skip


def finish(fig, ax, title: str, subtitle: str, note: str, output: Path) -> None:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=BASE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x / 1000:,.0f}k" if x else "0")
    height = fig.get_figheight()
    note = textwrap.fill(note, 150)
    # Reserve room for the axis title plus every footnote line, so they never overlap.
    fig.subplots_adjust(bottom=(0.75 + 0.15 * (note.count("\n") + 1)) / height)
    fig.text(0.01, 1 - 0.18 / height, title, ha="left", va="top", fontsize=18, color=INK)
    fig.text(0.01, 1 - 0.55 / height, subtitle, ha="left", va="top", fontsize=12, color=MUTED)
    fig.text(0.01, 0.06 / height, note, ha="left", va="bottom", fontsize=9.5, color=MUTED)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)


def catalogue_figure(catalogue: dict, output: Path) -> None:
    rows = {(r["config"], r["protocol"]): r for r in catalogue["catalogue"]}
    configs = [
        ("all", "All toolsets"),
        ("default", "Default toolsets"),
        ("read_only", "Read-only"),
        ("allowlist", "3-tool allowlist"),
    ]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    fig.subplots_adjust(left=0.17, right=0.97, top=1 - 1.0 / 5.2)
    for i, (key, name) in enumerate(configs):
        legacy, modern = rows[(key, "2025-11-25")], rows[(key, "2026-07-28")]
        d, o = legacy["declaration_tokens"], modern["output_schema_tokens"]
        ax.barh(i, d, color="#174EA6", height=0.62)
        ax.barh(i, o, left=d + 150, color="#D2E3FC", height=0.62, hatch="///", edgecolor="#4285F4", linewidth=0)
        ax.text(d + o + 600, i, f"{d:,} + {o:,}", va="center", color=INK, fontsize=11)
        ax.text(-400, i, f"{name}\n{legacy['tools']} tools", va="center", ha="right", fontsize=11.5)
    ax.set_yticks([])
    ax.invert_yaxis()
    ax.set_xlim(0, 72000)
    ax.set_xlabel("Reference tokens (o200k_base)", color=MUTED)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color="#174EA6"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#D2E3FC", hatch="///", edgecolor="#4285F4"),
    ]
    ax.legend(handles, ["Tool declarations: name, description, input schema", "Output schemas, offered only under MCP 2026-07-28"],
              loc="lower right", frameon=False, fontsize=10.5)  # fmt: skip
    finish(fig, ax, "One MCP server, 708 to 59,000 tokens",
           "GitHub MCP server v2.0.2: what its tool catalogue weighs before the agent does anything",
           "Compact JSON counted with o200k_base, a fixed ruler across configurations, not any provider's billing. Output schemas reach the model only if the client forwards them.",
           output)  # fmt: skip


def startup_figure(rows: list[dict], output: Path) -> None:
    first = {(s["agent"], s["condition"]): s["median_first_call_input"] for s in rows if s["task"] == "hello"}
    lines = []  # (agent header or None, condition, baseline, addition)
    for agent in AGENTS:
        if (agent, "none") not in first:
            continue
        lines.append((agent, None, 0, 0))
        base = first[(agent, "none")]
        for condition in ORDER[1:]:
            if (agent, condition) in first:
                lines.append((None, condition, base, first[(agent, condition)] - base))
    fig, ax = plt.subplots(figsize=(10.5, 0.36 * len(lines) + 1.8))
    fig.subplots_adjust(left=0.2, right=0.97, top=1 - 0.95 / (0.36 * len(lines) + 1.8))
    owner = None
    for y, (agent, condition, base, add) in enumerate(lines):
        if agent:
            owner = agent
            name, model = NAMES[agent]
            ax.text(-500, y, f"{name}", ha="right", va="center", fontsize=12.5, color="#174EA6")
            ax.text(
                0,
                y,
                f"  {model} · own prompt and tools: {first[(agent, 'none')]:,.0f}",
                va="center",
                fontsize=10.5,
                color=MUTED,
            )
            continue
        ax.barh(y, base, color=BASE, height=0.66)
        ax.barh(y, max(add, 0), left=base, color=COLORS[condition], height=0.66)
        ax.text(max(base, base + add) + 400, y, f"{add:+,.0f}", va="center", fontsize=10.5, color=INK)
        ax.text(-500, y, label(owner, condition), ha="right", va="center", fontsize=10.5)
    ax.set_yticks([])
    ax.invert_yaxis()
    ax.set_xlim(0, max(b + a for _, _, b, a in lines) * 1.12)
    ax.set_xlabel('Native input tokens of the first model request ("Reply with exactly OK")', color=MUTED)
    finish(fig, ax, "What an agent pays before its first useful action",
           "Gray: the agent's own prompt and tools. Color: what the GitHub MCP server's default tools or the gh skill add.",
           "Medians of 2 runs per bar, each agent's own tokenizer: compare bars within an agent, not across agents. Antigravity and ADK offer no deferral to switch off or on.",
           output)  # fmt: skip


def task_figure(rows: list[dict], task: str, title: str, subtitle: str, output: Path) -> None:
    lines = []
    for agent in AGENTS:
        cells = [s for s in rows if s["agent"] == agent and s["task"] == task]
        if not cells:
            continue
        lines.append((agent, None))
        lines += [(None, s) for s in sorted(cells, key=lambda s: ORDER.index(s["condition"]))]
    height = 0.34 * len(lines) + 1.8
    fig, ax = plt.subplots(figsize=(10.5, height))
    fig.subplots_adjust(left=0.2, right=0.97, top=1 - 0.95 / height)
    owner = None
    top = max((s["median_input"] or 0) for _, s in lines if s)
    for y, (agent, s) in enumerate(lines):
        if agent:
            owner = agent
            name, model = NAMES[agent]
            ax.text(-top * 0.012, y, name, ha="right", va="center", fontsize=12.5, color="#174EA6")
            ax.text(0, y, f"  {model}", va="center", fontsize=10.5, color=MUTED)
            continue
        value = s["median_input"] or 0
        failed = s["measured_on"] == "all"
        ax.barh(y, value, color="white" if failed else COLORS[s["condition"]], height=0.66,
                edgecolor=COLORS[s["condition"]], hatch="///" if failed else None, linewidth=1.2)  # fmt: skip
        passed = "" if s["passed"] == s["runs"] else f"   {s['passed']}/{s['runs']} passed"
        ax.text(value + top * 0.01, y, f"{value / 1000:,.{0 if value >= 10000 else 1}f}k{passed}", va="center", fontsize=10.5,
                color="#A50E0E" if passed else INK)  # fmt: skip
        ax.text(-top * 0.012, y, label(owner, s["condition"]), ha="right", va="center", fontsize=10.5)
    ax.set_yticks([])
    ax.invert_yaxis()
    ax.set_xlim(0, top * 1.18)
    ax.set_xlabel("Median cumulative native input tokens per run, every model call, cache included", color=MUTED)
    finish(fig, ax, title, subtitle,
           "Median of the passing runs out of 5; a hatched bar had no passing run and shows all runs. Each agent's own tokenizer: compare bars within an agent.",
           output)  # fmt: skip


def main() -> None:
    folder = Path(sys.argv[1])
    records = [json.loads(line) for line in (folder / "records.jsonl").read_text().splitlines() if line]
    catalogue = json.loads((folder / "catalogue.json").read_text())
    rows = summarize(records)
    summary = {
        "runs": len(records),
        "passed": sum(r["grade"]["passed"] for r in records),
        "framework_declarations": declarations(folder),
        "cells": rows,
    }
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (folder / "summary.md").write_text(table(rows))
    print(table(rows))
    print(json.dumps(summary["framework_declarations"]))
    style()
    figures = folder / "figures"
    catalogue_figure(catalogue, figures / "catalogue.png")
    startup_figure(rows, figures / "startup.png")
    task_figure(rows, "issue", "Investigating one issue: what each setup consumed",
                "Read GitHub issue #2275 and a pinned source file, then answer with a cited line range", figures / "issue.png")  # fmt: skip
    task_figure(rows, "release", "Looking up one release: what each setup consumed",
                "Return six metadata fields of the v1.12.2 release", figures / "release.png")  # fmt: skip


if __name__ == "__main__":
    main()
