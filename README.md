# MCP context benchmark

Reproducible measurements of how MCP tool catalogues reach agent context, using GitHub MCP server **v1.12.2** as a common input.

The default 45-tool input catalogue counts **10,989 reference tokens**; a three-tool allowlist counts **989**. Framework and CLI captures show how filtering and discovery change initial exposure. These are `o200k_base` reference counts, except for the separately labeled native Antigravity usage. They are not interchangeable with provider billing or complete-task cost.

![GitHub MCP catalogue sizes](figures/github-catalogue.png)

## Results at a glance

| Question | Observation | Unit | Evidence |
| --- | --- | --- | --- |
| How large is the GitHub catalogue? | 90 tools: 22,934; default 45: 10,989; read-only 26: 6,293; three-tool allowlist: 989 | `o200k_base` reference tokens, input declarations | [results.json](results.json) |
| What does host-side discovery remove at startup? | Claude Code 11,696 to 1,286; Codex CLI 11,365 to 923; goose 11,133 to 834 | Reference tokens added over each host's no-GitHub baseline | [data/](data/), [METHODS.md](METHODS.md) |
| Does provider-native search shrink the HTTP request? | No: LangChain's tool array held all 45 deferred definitions plus a search descriptor, 11,327 | Reference tokens, request bytes rather than model context | [data/langchain-provider-search.json](data/langchain-provider-search.json) |
| What does a CLI-first skill catalogue cost at startup? | 82 `fmind/dot` skills: 2,089; the `gh` skill: 29 until loaded, 687 for its loaded file | `o200k_base` reference tokens, skill names and descriptions | [data/cli-skills.json](data/cli-skills.json) |
| Eager versus discovery on one complete task | Only completed pair: 33,807 versus 14,067 (58.4% less); verdict inconclusive | Cumulative native input tokens | [task/results/](task/results/) |
| Eager, fixed role, and discovery on retrieval tasks | Two complete triplets: 17,177 / 1,391 / 2,010 and 17,988 / 2,262 / 2,048; verdict inconclusive | Cumulative native input tokens | [task/study-results/](task/study-results/README.md) |

Reference and native counts are different units. Do not rank hosts or frameworks across measurement surfaces.

## Reproduce the retained measurements

Requires [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv run --script analyze.py
```

This validates the retained controls and regenerates `results.json`, `catalogue.csv`, `checksums.json`, and the figure. No model credentials or inference are needed. The first invocation downloads pinned dependencies and the tokenizer encoding.

- [Results and measurement scopes](results.json)
- [Capture methods, versions, and rerun instructions](METHODS.md)
- [Sanitized provider and MCP observations](data/)
- [Release artifact URLs and verified checksums](data/environment.json)

Tested locally: LangChain/LangGraph, Google ADK, CrewAI, PydanticAI, Claude Code, Codex CLI, goose, and Antigravity CLI. Cursor and VS Code were not locally measured and are excluded from the numerical comparison.

## Complete GitHub task experiment

The reference harness in [task/](task/) compares eager exposure against deterministic tool discovery using **Gemini 3.8 Flash, low thinking**. It performs real read-only GitHub MCP calls, checks a pinned source file, and grades the answer independently of the model. Five paired trials, bounds, source projection, and grading rules are declared in [the plan](task/PLAN.md).

**Status: all ten planned attempts retained; verdict inconclusive.** Each strategy passed 2/5 attempts. Five attempts hit provider errors or a client timeout; one discovery answer had correct facts but violated the JSON-only format. The only pair where both passed used 33,807 input tokens eagerly versus 14,067 with discovery, a 58.4% reduction including search turns. See [every attempt, usage, latency, and limits](task/results/). No failures were replaced. This harness is a strategy comparison, not an end-to-end measurement of the named coding clients.

The analyzer requires positive integer input and total counts on every response before including a trial in medians or paired comparisons. Missing or invalid usage remains incomplete, even when the answer passes; available counts from partial trials are retained. The hardened analyzer reproduces the retained summary unchanged.

Recompute the task summary without inference:

```bash
python task/analyze_task.py task/results
```

To validate its logic without inference:

```bash
uv run --no-project --python 3.13.5 --with google-genai==2.24.0 --with mcp==2.2.0 \
  --with jsonschema==4.26.0 python -m unittest discover -s task -p 'test_*.py'
```

To run the paid experiment, download and verify the GitHub server specified in `data/environment.json`. Authenticate to your chosen GCP project with Application Default Credentials (ADC), and supply either `GITHUB_PERSONAL_ACCESS_TOKEN` through your secret manager or an authenticated `gh` installation. The provider is explicitly GCP; ambient API keys do not select another backend. Use a fresh output directory outside this repository:

```bash
mkdir /absolute/path/to/new-results
cp task/fixture.json /absolute/path/to/new-results/fixture.json
uv run --python 3.13.5 --script task/task_benchmark.py \
  --project YOUR_GCP_PROJECT --location global \
  --server /absolute/path/to/github-mcp-server \
  --output /absolute/path/to/new-results
python task/analyze_task.py /absolute/path/to/new-results
```

Seed the fresh directory with the retained fixture as shown: the runner rejects a changed observation when that file is present. Without it, the runner establishes a new fixture, which must not be silently pooled with these results.

This command uses account quota and performs model inference. The execution boundary rejects writes, other repositories, other issues, and unpinned source reads. Model retries are disabled; planned failures are retained. The task's model alias and live issue can change, so compare observed model versions and fixture digests before combining runs. These responses report only `gemini-3.8-flash`, not an immutable backend revision. Matching that alias is not proof that two runs used identical model weights.

## Three-strategy follow-up

[The follow-up study](task/STUDY.md) adds a fixed role allowlist and three initially held-out retrieval cases, with 54 declared trials, rotated ordering, first/repeat passes, and explicit cache-accounting limits. **Verdict: inconclusive.** It attempted 21 trials before the declared provider-failure stop, with 13 passes, seven HTTP 429/504 failures, and one strict-argument-gate failure; 33 remained unrun. Two complete matched comparisons show lower input usage for filtering and discovery. See [all results, interruptions, and limitations](task/study-results/README.md).

The initial run and the paced continuation retain their exact executed code. The current runners additionally accept the supported pinned `sha` spelling and block a conflicting SHA overriding `ref`; a read-only live control verifies equivalent source results. This post-run fix was not used for any reported model trial and did not change historical grades. The current authority revision cannot resume the earlier runs.

```bash
uv run --python 3.13.5 --script task/study.py
python task/analyze_study.py task/study-results
```

The first command validates offline; the second recomputes the result. Paid execution requires an authorized project and budget. The observed study used US$0.64 in conservative local accounting under a US$20 cap, not a verified invoice. No further inference is triggered by these commands.

## Scope and attribution

Startup evidence was collected on September 20, 2026; the separate complete-task experiment ran on September 21. Startup captures do not measure tool-search accuracy or full-task efficiency. In particular, a native provider can receive deferred schemas in its HTTP request while excluding them from the model's initial context. See [METHODS.md](METHODS.md) before ranking numbers across hosts.

Original benchmark code is MIT-licensed. Upstream schemas, source fixtures, and fonts retain their own notices in [THIRD_PARTY.md](THIRD_PARTY.md). Credentials, private prompts, conversation IDs, and third-party executables are not included. Raw new captures should be inspected and normalized before sharing.
