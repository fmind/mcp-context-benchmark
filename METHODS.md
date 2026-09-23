# Startup measurement methods

Measurements: 2026-09-20. Article revision: 2026-09-21. This is a startup-exposure experiment using the official GitHub MCP server, not a task-success, latency, or billing benchmark. All reported numbers can be recomputed from the retained data without a model account.

## Recompute the results

From the benchmark repository root:

```bash
uv run --script analyze.py
```

This validates the catalogues, writes `results.json`, `catalogue.csv`, and `checksums.json`, and regenerates `figures/github-catalogue.png`. The plot uses the bundled Google Sans font. `tiktoken 0.14.0` and `matplotlib 3.11.2` are pinned in the script. Its first invocation may download these packages and the tokenizer encoding; subsequent analysis is local.

`data/` contains sanitized observations, not constructed examples. `checksums.json` records SHA-256 for those files. Formatting JSON differently does not affect token calculations: the counter uses `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` and `o200k_base`. It includes JSON punctuation, rather than guessing a provider's internal prompt template.

## Repeat collection

Use an OS temporary directory. The capture scripts intentionally write beside themselves; copy them there rather than running them inside this evidence directory. Commands below assume Linux x86_64, `uv`, and Python 3.13.5. Keep at least 20 GiB free on the storage holding downloaded dependencies.

```bash
MCP_BENCH_SOURCE="$PWD"
MCP_BENCH_WORK=$(mktemp -d -t mcp-context-bench-XXXXXXXX)
cp "$MCP_BENCH_SOURCE"/scripts/*.py "$MCP_BENCH_WORK/"
cp "$MCP_BENCH_SOURCE"/scripts/codex-model.json "$MCP_BENCH_WORK/"
uv venv --python 3.13.5 "$MCP_BENCH_WORK/venv"
uv pip sync --python "$MCP_BENCH_WORK/venv/bin/python" \
  "$MCP_BENCH_SOURCE/requirements-frameworks.txt"
uv venv --python 3.13.5 "$MCP_BENCH_WORK/crew313-venv"
uv pip sync --python "$MCP_BENCH_WORK/crew313-venv/bin/python" \
  "$MCP_BENCH_SOURCE/requirements-crew.txt"
```

Download the two archives identified by URL and SHA-256 in `data/environment.json`. Verify their checksums before extraction. Put the GitHub executable at `$MCP_BENCH_WORK/github/github-mcp-server` and the goose GNU executable at `$MCP_BENCH_WORK/goose-gnu/goose`. Do not substitute the musl build: its Code Mode was unavailable in this experiment. The GitHub archive checksum was checked against the release's checksums file; the goose archive against its release asset digest.

Then collect real MCP catalogues and framework declarations, with no provider inference:

```bash
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/collect.py"
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/frameworks.py"
"$MCP_BENCH_WORK/crew313-venv/bin/python" "$MCP_BENCH_WORK/crew.py"
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/pydantic_wire.py"
```

Framework dependencies are frozen separately from CrewAI 1.15.22: the framework environment uses MCP SDK 2.2.0, while the CrewAI environment uses MCP SDK 1.28.1. The first environment includes an incidental CrewAI 1.6.1 installation, which was **not** the version tested in the CrewAI row. The dedicated Python 3.13 environment avoids the Python 3.14 import failure encountered through CrewAI's ChromaDB/Pydantic-v1 dependency path. The retained LangChain experiment uses its built-in beta `MCPAdapter`; the separately installed `langchain-mcp-adapters 0.3.1` failed to import with MCP 2.2.0 and is not the adapter measured.

For the host captures, install Claude Code 2.1.274 and Codex CLI 0.154.0 on `PATH`. The current Codex script requires the bundled `scripts/codex-model.json`, derived from the [0.154.0 public model catalogue](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/models-manager/models.json). Its upstream `base_instructions` are replaced with a fixed benchmark instruction and `model_messages` is null; capability fields are retained. Each variant gets an isolated `CODEX_HOME` and `XDG_CONFIG_HOME`; only `supports_search_tool` changes between its model fixtures. The script checks the CLI version, refuses an existing output directory, and records the fixture hash and UTC capture time in `codex-payloads/provenance.json`.

This is a new reproducible control. The September 20 Codex captures used the then-current local `gpt-5.5` cache entry and user configuration, which were not retained. The new fixture cannot reconstruct that missing historical state, and new captures must not silently replace `data/codex-*.json`. A [separate September 21 validation](validation/codex-2026-09-21/provenance.json) with the public fixture reproduced all three historical tool arrays exactly, including their 11,365-token eager and 923-token deferred additions. It records the fixture and script hashes with the new capture time. Then run:

```bash
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/capture_claude.py"
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/capture_codex.py"
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/capture_goose.py"
```

Claude Code tool search is forced with `ENABLE_TOOL_SEARCH=true` in the deferred variant: a custom API endpoint can otherwise disable it. The eager variant sets `ENABLE_TOOL_SEARCH=false`.

The clients send to loopback HTTP servers, with dummy provider credentials and no inference. The endpoint deliberately returns HTTP 400 after capturing the request. Consequently, a nonzero CLI exit is expected; it is not a successful model invocation. goose retried four times; the analysis counts the first request, never their sum. An empty capture, missing GitHub catalogue, or absent Code Mode is a failed experiment, not a zero-token result. The analyzer validates these controls for the retained captures.

The original startup study's live model experiment uses an existing Antigravity native subscription. It consumes account quota, depends on the user's installed client and settings, and is not run by any other script:

```bash
# Requires agy 1.2.7, logged in, with gemini-3.8-flash-high available.
mkdir -p "$MCP_BENCH_WORK/agy-work"
git -C "$MCP_BENCH_WORK/agy-work" init -q
"$MCP_BENCH_WORK/venv/bin/python" "$MCP_BENCH_WORK/measure_agy.py"
```

The script uses a temporary project configuration and `--new-project`; it does not edit global configuration. The client can still retain session/cache state in its normal user directories. It asks for `OK`, with no tool calls, and checks the server's protocol log independently. Preserve cache fields separately. The released CLI's `total_tokens` field is retained verbatim, not reinterpreted as total context occupancy.

Keep raw new runs local: client diagnostics or prompts may contain user instructions, local paths, or session identifiers. The committed evidence removes process logs, account metadata, conversation IDs, private instructions, and absolute scratch paths. Never copy new raw results wholesale over `data/`.

Normalize and analyze a fresh collection without replacing the retained results:

```bash
python "$MCP_BENCH_SOURCE/normalize.py" \
  "$MCP_BENCH_WORK" "$MCP_BENCH_WORK/normalized-data"
MCP_BENCH_DATA="$MCP_BENCH_WORK/normalized-data" \
MCP_BENCH_OUTPUT="$MCP_BENCH_WORK/analysis" \
  uv run --script "$MCP_BENCH_SOURCE/analyze.py"
```

The normalizer fails on missing host captures and omits Antigravity when the optional live experiment was not run. It never substitutes old native usage into a new result. The analyzer still validates catalogue and host controls. Review newly normalized content before sharing it; the CLI versions and user configuration must match the intended comparison.

## What each number means

| Evidence | Measurement boundary | Limit |
| --- | --- | --- |
| `github-*.json` | Actual MCP discovery, serialized through MCP 2.2.0 | Entire records include output schemas and SDK-inserted defaults; not all fields enter prompts |
| `langchain-*.json`, `langgraph-bound-tools.json` | Real adapter, provider serialization, graph binding, and executed middleware with capture models | No model inference or tool-selection accuracy measurement |
| `adk-*.json` | Real `McpToolset` function declarations | Excludes Gemini request framing |
| `crewai-*.json` | Real `MCPToolResolver` and generated Pydantic input schema | Before provider conversion; `original_name` is instrumentation and excluded from counting |
| `pydantic-wire-*.json` | Real Anthropic adapter with a mock HTTP transport | Fake response usage is zero and is never used as a measurement |
| `pydantic-deferred.json` | Actual local-search fallback with a capture model | Intermediate tool dataclass, not a provider-native token count |
| `claude-*.json` | First HTTP request's system, messages, and tools | Fixed benchmark system prompt; scratch work directory normalized to `/benchmark` |
| `codex-*.json` | First HTTP request's tools | Excludes instructions and messages; eager variant deliberately disables model search capability |
| `goose-*.json` | First HTTP request's tools | Excludes instructions and messages; Code Mode is enabled through a recipe |
| `antigravity.json` | Actual native usage and extracted server-log discovery evidence | Six diagnostic runs; no task-quality benchmark or cross-tokenizer ratio |

The eager host tests have the same 45 GitHub tool names. GitHub MCP v1.12.2 exposes `delete_repository` only when both MCP `2026-07-28` and form elicitation are supported; the harness tests pass `--exclude-tools=delete_repository` to neutralize that difference. `collect.py` and the task runner call legacy `initialize()` and negotiate `2025-11-25`. Independent controls on September 21 returned 45 tools for legacy initialization with or without elicitation, 45 for modern discovery without elicitation, and 46 for modern discovery with elicitation. The current tools specification describes the general mechanism, not the negotiated protocol of every measurement. Actual credentials and server permissions can change the available catalogue; this experiment uses a dummy credential and never calls GitHub operations.

The native-provider search request still contains all 45 definitions marked `defer_loading`, plus a search descriptor. These bytes are not proof that the model initially receives the definitions. Conversely, the reference-token size of the small search descriptor is not the provider's complete search overhead. Do not rank it as a nearly free prompt.

Antigravity's valid order was baseline, default, all, focused, default, baseline. The first default observation was cached; the second was uncached. The article uses the two uncached baseline observations to show a range, rather than deriving confidence intervals from this small sample. Earlier disconnected probes were discarded after the server log showed the project configuration had not loaded. They are excluded from the retained dataset.

## Coverage and primary sources

| Subject | Evidence and source |
| --- | --- |
| GitHub configuration and toolsets | [Pinned v1.12.2 release](https://github.com/github/github-mcp-server/releases/tag/v1.12.2), actual executable catalogues |
| MCP discovery semantics | [2026-07-28 tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) |
| LangChain selector/native deferral | [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in), installed source and executed middleware |
| ADK filtering/history | [MCP tools](https://adk.dev/tools-custom/mcp-tools/), [compaction](https://adk.dev/context/compaction/) |
| CrewAI filtering/history | [1.15.22 MCP](https://docs.crewai.com/v1.15.22/en/mcp/overview), [agent controls](https://docs.crewai.com/v1.15.22/en/concepts/agents) |
| PydanticAI deferral | [Tool search](https://pydantic.dev/docs/ai/capabilities/tool-search/), installed source and captured provider request |
| Claude Code defaults | [MCP documentation](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search), actual CLI request |
| Codex model capability gate | [Pinned spec plan](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/tools/spec_plan.rs), actual CLI request |
| goose feature/build behavior | [Code Mode guide](https://goose-docs.ai/docs/guides/managing-tools/code-mode/), [v1.51.0 release](https://github.com/aaif-goose/goose/releases/tag/v1.51.0), GNU and musl executable probes |
| Antigravity configuration | [CLI MCP configuration](https://antigravity.google/docs/mcp?tab=cli), actual native CLI and server log |
| Cursor | [Vendor discovery experiment](https://cursor.com/blog/dynamic-context-discovery); editor unavailable, no local measurement |
| VS Code Copilot | [Tool controls](https://code.visualstudio.com/docs/agents/run/tools); editor unavailable, no local measurement |
| Web/cloud products, gateways, A2A, AGENTS.md | Outside the numerical comparison; no execution/token benchmark |

`original-link-audit.json` retains status, redirect target, and response digest for the original draft's links and selected version lookups. Seven original server links returned HTTP 404. The old ten-server table had no pinned versions, counting code, or retained raw payloads, and cannot support a current numerical comparison. It is replaced by the controlled GitHub experiment; no claim is made that those ten legacy server configurations were reproduced.

Schemas and built-in tool descriptions remain attributable to their upstream projects. The GitHub server is [MIT-licensed](https://github.com/github/github-mcp-server/blob/v1.12.2/LICENSE). No third-party binaries, complete documentation pages, credentials, or private user prompts are redistributed here.

The public home is [fmind/mcp-context-benchmark](https://github.com/fmind/mcp-context-benchmark). Preserve the data, versions, scope labels, and checksums together.

## Follow-up task study and reference handling

The separate [three-strategy study](task/STUDY.md) has [complete outcome and usage records](task/study-results/README.md), including the initial interruption and operational amendment. Its role allowlist differs from the startup subset, and its first/repeat passes do not impose cache state.

The executed runners are archived beside their results. Current task runners accept either `ref` or `sha` for the pinned commit and reject conflicting references, following the GitHub tool's supported [reference parameters](https://github.com/github/github-mcp-server/blob/v1.12.2/pkg/github/repositories.go#L966-L974). The [live alias control](validation/github-reference-alias-2026-09-21.json) fetched both source files with both spellings and obtained identical projected hashes. This post-run correction preserves the declared strict-gate failure and every historical observation. The original runner and its hash are also available in the original public benchmark revision; current source is not a byte-identical reconstruction of it.

## CLI-first skill comparison

[`scripts/skills_index.py`](scripts/skills_index.py) counts the agent skills of [fmind/dot](https://github.com/fmind/dot) at a pinned commit, reading `git show` output rather than a working tree. Each skill contributes its `name` and `description`, serialized as compact JSON with sorted keys and counted with `tiktoken 0.14.0` and `o200k_base`, like the MCP declarations. It also counts the complete `gh` skill file, which a host loads only when the skill is selected. Run it against a local clone:

```bash
git clone https://github.com/fmind/dot /absolute/path/to/dot
uv run --script scripts/skills_index.py /absolute/path/to/dot
```

This index count excludes host framing. [`scripts/capture_claude_skills.py`](scripts/capture_claude_skills.py) measures the host view: Claude Code's first request, captured on loopback without inference like the original host captures, in six variants from one installed version and one flag set: baseline, GitHub MCP eager, GitHub MCP with tool search, the `gh` skill alone, all skills, and all skills with `SLASH_COMMAND_TOOL_CHAR_BUDGET=100000`. Claude Code [budgets skill metadata](https://code.claude.com/docs/en/env-vars) at 1% of the context window with an 8,000-character fallback and drops descriptions on overflow; the last variant lifts that budget. Skills that set `disable-model-invocation` are installed but not listed, and a skill named like a built-in replaces it; `provenance.json` records both. Three consecutive runs on September 22, 2026 produced byte-identical requests, and the MCP variants reproduced the September 20 additions within one token on the newer CLI.

```bash
python scripts/capture_claude_skills.py /absolute/path/to/dot /absolute/path/to/github-mcp-server /absolute/path/to/new-dir
uv run --script analyze_cli.py
```

[`scripts/cli_outputs.py`](scripts/cli_outputs.py) runs read-only `gh` commands and GitHub MCP v1.12.2 calls for issue #2275 and the pinned `pkg/github/tools.go`, with the authenticated `gh` account for both. It retains byte sizes, digests, and `o200k_base` counts of the raw text, never the issue or source content. MCP results count text items and embedded resource text, before any client projection. The issue is live and can change; the file reads are pinned.

These measurements do not compare capability: the `gh` CLI and the GitHub MCP server expose different operations, authentication, and output shapes. No complete CLI task with a model was run.

