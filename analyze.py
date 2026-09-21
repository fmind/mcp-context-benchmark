# /// script
# requires-python = ">=3.13"
# dependencies = ["tiktoken==0.14.0", "matplotlib==3.11.2"]
# ///
"""Recompute article numbers and figure from the retained, sanitized captures."""

import csv
import hashlib
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import tiktoken
from matplotlib import font_manager

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("MCP_BENCH_DATA", ROOT / "data"))
OUTPUT = Path(os.environ.get("MCP_BENCH_OUTPUT", ROOT))
ENCODING = tiktoken.get_encoding("o200k_base")


def read(name: str) -> dict | list:
    """Read one evidence file."""
    return json.loads((DATA / f"{name}.json").read_text())


def tokens(value: object) -> int:
    """Count a stable JSON representation, not a provider's hidden prompt."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return len(ENCODING.encode(text))


def require(condition: bool, message: str) -> None:
    """Reject invalid experimental controls."""
    if not condition:
        raise ValueError(message)


def main() -> None:
    """Validate catalogue controls, calculate counts, and render the chart."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalogues = []
    for mode, expected in [("default", 45), ("all", 90), ("read_only", 26), ("focused", 3)]:
        tools = read(f"github-{mode}")["tools"]
        require(len(tools) == expected, f"Unexpected GitHub {mode} count")
        declarations = [
            {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]} for t in tools
        ]
        catalogues.append(
            {
                "mode": mode,
                "tools": len(tools),
                "input_schema_tokens": tokens(declarations),
                "full_record_tokens": tokens(tools),
            }
        )
    expected_names = {t["name"] for t in read("github-default")["tools"]}
    focused_names = {t["name"] for t in read("github-focused")["tools"]}
    frameworks = []
    for framework in ["langchain", "adk", "crewai", "pydantic-wire"]:
        row = {"framework": framework}
        for mode, names in [("eager", expected_names), ("focused", focused_names)]:
            payload = read(f"{framework}-{mode}")
            if framework == "crewai":
                actual = {t["original_name"] for t in payload}
                declarations = [{k: t[k] for k in ["name", "description", "parameters"]} for t in payload]
            else:
                declarations = payload["function_declarations" if framework == "adk" else "tools"]
                actual = {t["name"] for t in declarations}
            require(actual == names, f"Catalogue mismatch: {framework}/{mode}")
            row[f"{mode}_tokens"] = tokens(declarations)
        frameworks.append(row)
    require({t["name"] for t in read("langgraph-bound-tools")["tools"]} == expected_names, "LangGraph mismatch")
    for name in ["langchain-provider-search", "pydantic-wire-deferred"]:
        tools = read(name)["tools"]
        require({t["name"] for t in tools if t.get("defer_loading")} == expected_names, f"Deferral mismatch: {name}")
    hosts = []
    for host, optimized in [("claude", "deferred"), ("codex", "deferred"), ("goose", "code_mode")]:
        base = read(f"{host}-baseline")
        eager = read(f"{host}-eager")
        deferred = read(f"{host}-{optimized}")
        if host == "claude":
            require(
                {t["name"].removeprefix("mcp__github__") for t in eager["tools"]} == expected_names, "Claude mismatch"
            )
            require(len(deferred["tools"]) == 2, "Claude deferred schemas unexpectedly loaded")
            scope = "JSON system + messages + tools; work directory normalized to /benchmark"
        else:
            scope = "JSON tools array only; excludes messages and system instructions"
            if host == "goose":
                require(
                    {t["name"].removeprefix("github__") for t in eager["tools"]} == expected_names, "goose mismatch"
                )
                require(len(deferred["tools"]) == 3, "goose Code Mode unavailable")
            else:
                namespace = next(t for t in eager["tools"] if t.get("name") == "mcp__github")
                require({t["name"] for t in namespace["tools"]} == expected_names, "Codex namespace mismatch")
                require(not any(t.get("name") == "mcp__github" for t in deferred["tools"]), "Codex not deferred")
            base, eager, deferred = base["tools"], eager["tools"], deferred["tools"]
        b, e, d = tokens(base), tokens(eager), tokens(deferred)
        hosts.append(
            {
                "host": host,
                "scope": scope,
                "baseline": b,
                "eager": e,
                "optimized": d,
                "eager_delta": e - b,
                "optimized_delta": d - b,
                "delta_reduction_percent": round(100 * (1 - (d - b) / (e - b)), 2),
            }
        )
    agy = read("antigravity") if (DATA / "antigravity.json").is_file() else []
    for row in agy:
        names = set(row["mcp_tool_names"])
        expected = set() if row["mode"] == "baseline" else {t["name"] for t in read(f"github-{row['mode']}")["tools"]}
        require(names == expected, f"Antigravity catalogue mismatch {row['index']}")
        require(
            row["status"] == "SUCCESS" and row["num_turns"] == 1 and row["tools_call_count"] == 0,
            "Invalid Antigravity probe",
        )
    result = {
        "catalogues": catalogues,
        "frameworks": frameworks,
        "hosts": hosts,
        "selector_payload_reference_tokens": tokens(read("langchain-selector-request")),
        "native_search_wire_tokens": tokens(read("langchain-provider-search")["tools"]),
        "antigravity": agy,
    }
    controls = [
        row["usage"]["input_tokens"]
        for row in agy
        if row["mode"] == "baseline" and row["usage"]["cache_read_tokens"] == 0
    ]
    result["antigravity_uncached_input_range"] = [min(controls), max(controls)] if controls else None
    # The raw usage above is the authority; never add cached tokens without a provider contract.
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    with (OUTPUT / "catalogue.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(catalogues[0]))
        writer.writeheader()
        writer.writerows(catalogues)
    font = ROOT / "assets/fonts/GoogleSans-Regular.ttf"
    require(font.is_file(), "The bundled Google Sans font is required")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update(
        {"font.family": "Google Sans", "font.size": 12, "text.color": "#202124", "axes.labelcolor": "#202124"}
    )
    fig, ax = plt.subplots(figsize=(10, 5.2), layout="constrained")
    modes = [catalogues[i] for i in [1, 0, 2, 3]]
    labels = [
        "All toolsets (90 tools)",
        "Default (45 tools)",
        "Read-only default (26 tools)",
        "Focused allowlist (3 tools)",
    ]
    bars = ax.barh(labels, [r["input_schema_tokens"] for r in modes], color=["#174EA6"] * 3 + ["#0D652D"])
    ax.invert_yaxis()
    ax.bar_label(bars, labels=[f"{r['input_schema_tokens']:,}" for r in modes], padding=8, color="#202124")
    ax.set_xlim(0, 28000)
    ax.set_xlabel("Reference tokens in input tool declarations (o200k_base)")
    ax.set_title("One GitHub MCP server, four catalogue sizes", loc="left", fontsize=18, pad=20)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0)
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
    fig.text(
        0.03,
        -0.04,
        "GitHub MCP v1.12.2 | 20 September 2026 | Excludes outputs, history and provider framing",
        fontsize=10,
        color="#595D62",
    )
    output = Path(os.environ.get("MCP_BENCH_FIGURES", OUTPUT / "figures")) / "github-catalogue.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    checksums = {
        str(path.relative_to(DATA)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(DATA.glob("*.json"))
    }
    (OUTPUT / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")


if __name__ == "__main__":
    main()
