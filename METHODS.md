# Methods

Measurements: 2026-10-10. One MCP server, two GitHub tasks, six agents, up to five ways to give the agent GitHub: the MCP server loaded eagerly, the agent's own default, framework-side tool search where one exists, a three-tool allowlist, or no MCP at all and the `gh` CLI with a skill. Every number comes from the agent's own usage report, except the catalogue and result sizes, which use a fixed reference tokenizer and no model.

## Agents

| Agent | Kind | Version | Model and effort | Conditions |
| --- | --- | --- | --- | --- |
| Claude Code | harness | 2.1.295 | `claude-sonnet-5-5`, `--effort low` | none, default, eager, allowlist, cli |
| Codex CLI | harness | 0.162.0 | `gpt-6-luna`, reasoning effort low | none, default, eager, allowlist, cli |
| Antigravity CLI | harness | 1.3.3 | `gemini-3.8-flash-low`, `--effort low` | none, default, allowlist, cli |
| LangGraph | framework | langchain 1.4.4, langgraph 1.2.14, langchain-mcp-adapters 0.3.2, langchain-google-genai 4.4.0, mcp 1.30.0 | Gemini 3.8 Flash on Vertex AI, thinking level low | none, eager, search, allowlist, cli |
| Google ADK | framework | google-adk 2.11.0, mcp 2.3.0 | Gemini 3.8 Flash on Vertex AI, thinking level low | none, eager, allowlist, cli |
| PydanticAI | framework | pydantic-ai-slim 2.55.0, fastmcp-slim 4.1.0, mcp 2.3.0 | Gemini 3.8 Flash on Vertex AI, thinking level low | none, eager, search, allowlist, cli |

The harnesses ran on the author's subscriptions; the frameworks on a Vertex AI project in the `global` location. Antigravity CLI and the three frameworks share one model, so they can be compared on ratios and behavior; Claude Code and Codex CLI each run their vendor's model. Anthropic models were not reachable on the Vertex AI project, so the frameworks were not tested with Claude. Each framework script pins its dependencies with PEP 723; `uv` resolves them on first run.

The MCP server is the official [GitHub MCP server v2.0.2](https://github.com/github/github-mcp-server/releases/tag/v2.0.2), Linux x86_64. Its archive matched the release's checksums file (SHA-256 `815e27d931c796af0c97f24fd211e14f8a4607d4528377719a5ad2352086b0b0`); the extracted binary's digest and build are recorded in [`results/catalogue.json`](results/catalogue.json).

## Conditions

- **none**: no GitHub access. Its single request sets the agent's own baseline: system prompt and built-in tools.
- **default**: the server's 46 default tools, the harness left untouched. The server adds a 47th, `delete_repository`, for clients that use MCP 2026-07-28 and support form elicitation: Claude Code and Antigravity CLI listed 47 tools, in this condition and in eager. The gate would have rejected any call to it. Claude Code and Codex CLI defer MCP tools behind a search tool by default; Antigravity CLI routes every MCP server through one `call_mcp_tool` gateway and writes each tool's schema to a file the model can read.
- **eager**: the same server with every definition in every request. `ENABLE_TOOL_SEARCH=false` for Claude Code, `supports_search_tool=false` in the model catalogue for Codex CLI. Antigravity CLI has no such switch. For a framework, eager is its untouched default.
- **search**: framework-side discovery. LangGraph uses `LLMToolSelectorMiddleware(max_tools=3)`, a model call that selects tools before each agent step; LangChain's provider-native tool search supports only Anthropic and OpenAI. On `hello`, LangGraph's first request is therefore the selector's call. PydanticAI uses `toolset.defer_loading()`, which hides every tool behind its local `search_tools` function. ADK has no discovery option for MCP tools.
- **allowlist**: three tools, `issue_read`, `get_file_contents`, and `get_release_by_tag`, which cover both tasks. Harnesses start the server with `--toolsets= --tools=...`; frameworks filter with their own API (`tool_filter`, `filtered`, a list comprehension).
- **cli**: no MCP server. The authenticated `gh` CLI and the [`gh` skill](bench/skills/gh/SKILL.md) from [fmind/dot](https://github.com/fmind/dot/tree/4d65e1f591ce50f46bac407d2a27622abd0bffd1/skills/gh). Harnesses discover the skill in their project skill directory. Frameworks get one `run_shell` tool, which returns exit code, stdout, and stderr truncated at 30,000 characters, and the skill's name, description, and path in their instructions.

## Tasks

The prompts and answer key are in [`bench/common.py`](bench/common.py).

- **hello**: "Reply with exactly OK. Do not use any tools." Its single request measures startup context. Two repetitions per condition.
- **issue**: read [issue #2275](https://github.com/github/github-mcp-server/issues/2275) and `pkg/github/tools.go` at a pinned commit, then report whether the `projects` toolset is enabled by default, with a cited line range and quote. Five repetitions.
- **release**: report six metadata fields of the [v1.12.2 release](https://github.com/github/github-mcp-server/releases/tag/v1.12.2): tag, name, author, publication date, prerelease, and draft. Five repetitions.

The release task asks only for fields present in both of the server's result shapes. Under MCP 2026-07-28, v2.0.2's typed `get_release_by_tag` result omits the release's assets (see [catalogue](#catalogue-and-results)); an earlier draft that asked for an asset digest could not be answered through that tool by clients negotiating the new protocol.

Conditions rotate within each repetition. The six agents ran in parallel, each one sequentially. Every run stops after 420 seconds; a framework run also stops after 25 model calls, and its `run_shell` commands after 60 seconds. Nothing was retried or replaced, except provider HTTP 429 and 5xx responses (500, 502, 503, 504) inside a framework run, which the harness retries with backoff and counts (none occurred). Transport failures, such as a dropped connection, are not retried: two CLI runs ended that way and are kept as failures.

## Isolation and authority

Every run gets a fresh Git workspace under a run directory outside this repository. Claude Code and Codex CLI also get a fresh home (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`), so user instructions, skills, plugins, hooks, and memories do not load; Codex CLI receives a copy of its login file, deleted when it exits. Antigravity CLI has no documented equivalent and runs with the user's home, constant across its conditions.

GitHub access is read-only by construction, not by prompt:

- [`gate.py`](bench/gate.py) sits between the agent and the MCP server. It forwards discovery unchanged, so each agent sees the real catalogue, and rejects any `tools/call` outside `get_*`, `list_*`, `search_*`, `issue_read`, and `pull_request_read`. It refuses JSON-RPC batches. It logs each call's name, arguments, outcome, and result size, the protocol version the client requested (in `initialize`, or on every request under 2026-07-28), and the listed tool names. The GitHub token comes from `gh auth token` and exists only in the server's environment.
- [`gh_shim.py`](bench/gh_shim.py) is first on `PATH`. In MCP conditions it refuses every command. In the CLI condition it forwards only read commands and `GET` API calls to the real `gh`.

The prompt also forbids reaching GitHub any other way. The analysis fails a run for two kinds of evidence. The first is a shell command that uses a known network tool outside the designated interface: `curl`, `wget`, Git's network subcommands, HTTP or socket libraries, or the real `gh` called by path or through `mise`, which would skip the shim. The second is a path outside the run in the agent's event stream: a home path written in full, with `~` or with `$HOME`, a climb two levels out of the workspace, or a second Antigravity conversation. `collect.py` re-applies both audits to every raw stream. No run was flagged.

## Grading

A run passes when its final answer is a JSON object with every fact correct, the agent made a successful read through the designated interface (each required MCP tool, `issue_read` and `get_file_contents` or `get_release_by_tag`, called at least once; or a `gh` command naming the issue number and `tools.go`, or the release tag), the gate or shim blocked nothing, and neither audit flagged the run. The answer may be wrapped in a Markdown fence; strict JSON-only output is recorded separately as `strict_format`. For the issue task, the line range and quote are recorded as `citation` and do not affect the pass. Issue state is compared case-insensitively.

## Measurements

- `first_call_input`: native input tokens of the first model request, cache included. On `hello` this is the startup context.
- `input`: cumulative native input across every model request in the run, cache included. It measures how much context the model processed, not a bill: cached input is usually charged at a fraction of the price.
- `cache_read`, `output`, `reasoning`: as reported.
- `citation`: on the issue task, whether the answer's line range is exact and its quote matches up to whitespace. Runs that ended without an answer count as misses.
- Token, call, and output medians use the passing runs of a cell, or all its runs when none passed; pass counts, wall time, and GitHub call medians use every run.
- `model_calls`: Claude Code assistant messages deduplicated by message ID, Codex CLI `token_count` records, Antigravity CLI steps with usage, and every google-genai response for the frameworks, including LangGraph's selector calls.

Framework usage is read from every google-genai response, the client all three frameworks use, by wrapping its `generate_content` methods: one capture for the three frameworks, independent of their callbacks. The first request's function declarations are kept under [`results/declarations/`](results/declarations/).

Each agent counts with its own tokenizer. Compare conditions within an agent; across agents, compare ratios and behavior.

## Catalogue and results

[`bench/catalogue.py`](bench/catalogue.py) runs no model. It lists the server's tools in four configurations, negotiated as MCP 2025-11-25 (initialize) and as 2026-07-28 (stateless `_meta`), and calls the three task tools read-only under both versions, next to the `gh` commands that return the same data. It counts compact sorted JSON or raw text with `tiktoken 0.14.0` and `o200k_base`, a fixed ruler across configurations, not a provider's count. It keeps sizes and digests, never content.

## Reproduce

Requires [uv](https://docs.astral.sh/uv/), an authenticated `gh`, the three harnesses on `PATH` with their own logins, and Application Default Credentials for a Vertex AI project. Keep the run directory **outside this repository**: an agent that can read its parent directories can find the answer key.

```bash
export GITHUB_MCP_SERVER=/absolute/path/to/verified/github-mcp-server   # v2.0.2
export GOOGLE_CLOUD_PROJECT=your-vertex-project
OUT=/absolute/path/outside/the/repository
for agent in claude codex agy langgraph adk pydantic; do python3 bench/study.py "$OUT" "$agent" & done; wait
python3 bench/collect.py "$OUT" results
uv run --script bench/catalogue.py results/catalogue.json
uv run --script bench/analyze.py results
```

This performs model inference on your subscriptions and project, and real read-only GitHub calls with your `gh` login. `study.py` resumes after completed runs and never replaces a failed one. The run directory holds raw agent streams, which can contain local paths and session identifiers; `collect.py` re-audits them and writes the sanitized copy. The offline tests need no credentials:

```bash
python3 -m unittest discover -s bench -p 'test_*.py'
```

## Limits

- Five repetitions per cell show direction and spread, not statistical significance.
- Two tasks with supplied identifiers. They do not test open-ended exploration of an unfamiliar repository.
- The agents, models, and GitHub issue are live and can change. Model aliases do not identify immutable weights; Antigravity CLI updates itself.
- Each agent ran one small model at low effort. Larger models may search, verify, and bypass differently.
- The frameworks ran Gemini only. Their numbers say nothing about Claude or GPT models behind the same adapters.
- Harnesses keep their shell in MCP conditions (with `gh` refused); frameworks in MCP conditions have only the MCP tools.
- The MCP client library decides the protocol version, and the protocol decides the result shape: PydanticAI (FastMCP) negotiated 2026-07-28 and received typed results, LangGraph and ADK negotiated 2025-11-25 and received full JSON. Framework differences on complete tasks include that effect, not only the adapters' tool handling.
- Codex CLI's sandbox may write to the run's log folder, which also holds the gate and shim logs; the audits read the raw event stream, not only those logs.
- The gate's `result_chars` counts text content only, not `structuredContent`; no figure uses it.
- Prompt caching depends on provider state across runs. Cumulative input includes cached tokens so that conditions stay comparable; cost does not follow directly from it.

The [September 2026 edition](https://github.com/fmind/mcp-context-benchmark/tree/v1.1.0) measured GitHub MCP server v1.12.2 with earlier agent versions, CrewAI, goose, and a reference task harness; it remains in this repository's history.
