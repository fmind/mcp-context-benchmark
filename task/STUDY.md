# Three-strategy follow-up study

Status: executed with interruption: 21 attempted, 33 not run; see [results](study-results/README.md). The archived plans in each result directory preserve the exact declarations before those executions. Declared on 2026-09-21, before any inference on these cases. The original `PLAN.md`, runner, fixtures, and ten results remain historical evidence.

## Decision and scope

Compare eager exposure, a fixed role allowlist, and keyword discovery on three held-out GitHub retrieval tasks. The decision concerns these bounded tasks, not general GitHub competence or the named coding agents. The original issue-2275 task is the development case and is excluded.

The author inspected source observations to establish expected answers. No model has attempted the new cases during preparation. Do not tune prompts, search weights, limits, or grading after seeing their model results and still describe them as held out. An amended study needs a new identity and must retain the failed attempts.

## Frozen conditions

- Provider/model: GCP in `global`, ADC, `gemini-3.8-flash`, low thinking, 2,048 output-token limit, temperature omitted, no model retries or fallback. The alias is not an immutable backend revision; retain returned versions.
- Runtime: Python 3.13.5, Google Gen AI SDK 2.24.0, MCP SDK 2.2.0, jsonschema 4.26.0. Execute with the pinned PEP 723 command below. The runner records actual versions and hashes of code, case fixtures, plan, server binary, and catalogue.
- Server: GitHub MCP v1.12.2, verified Linux x86_64 archive from `data/environment.json`. `initialize()` negotiates MCP `2025-11-25`. The live catalogue must equal the retained 45-tool control before inference.
- Eager: all 45 declarations. Fixed: `get_file_contents`, `issue_read`, `get_release_by_tag`, selected for a source/issue/release inspection role before model trials. This is a different three-tool subset from the article's 989-token startup subset, which includes `search_code`; never reuse that number for this condition. Discovery: the original keyword scorer, one `search_tools` function initially, up to three matching tools loaded per search and retained within that trial.
- Tool authority: exact read operations and arguments recorded per case; all other attempted operations are blocked and fail grading. Visible definitions do not expand execution authority. No GitHub writes.
- Evidence: real read-only MCP calls, projected identically across strategies. Every result must match its frozen projected observation. Issue authors, bodies, and unrelated metadata are omitted. The complete `go.mod` is retained with line numbers; all release asset names, sizes, and digests are retained so the model must select the requested architecture. A changed issue or release observation aborts preflight, rather than silently updating a held-out case.

## Cases and answer checks

| Case | Task | Deterministic evidence check |
| --- | --- | --- |
| source | Read `go.mod` at commit `85598ba6e1256f7ebf4867b95d63b833c4549264`; identify Go and MCP Go SDK versions | Exact version strings, path, commit, dependency line number, and whitespace-normalized complete dependency line |
| issue | Read issue `github/github-mcp-server#2250` | Exact observed number, title, state, and URL |
| release | Inspect release `v1.12.2`, selecting the Linux x86_64 archive | Exact tag, publication timestamp, draft/prerelease booleans, asset name, bytes, and algorithm-prefixed digest |

`study-cases.json` contains prompts, expected answers, projected observations, their hashes, source URLs, and the preparation timestamp. The grader checks JSON syntax, field values and types, a successful evidence read, and no blocked calls. Markdown fences fail the same output contract as the original study. Extra JSON keys are tolerated. These cases test lookup and tool routing with supplied identifiers; they do not test repository search, long investigations, adversarial content, or output filtering.

## Trials and cache conditions

Three cases x three strategies x three blocks x two passes = **54 planned trials**. Strategy order rotates by case and block, giving each strategy each position once per case. Within a strategy, a first trial is immediately followed by a repeat of the identical task. Both start with fresh conversation and loaded-tool state. No failures are replaced. The MCP session is reused; server startup and catalogue collection are outside timed trials.

Caching stays provider-managed. No explicit cache object is created; no project cache setting is changed. Google's [cache documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/context-cache/context-cache-overview), checked on 2026-09-21, documents implicit caching by default. Shared prefixes may be reused across strategies, cases, and blocks. **First and repeat do not mean cold and warm.** Retain native cache fields for every response; distinguish positive cache hits, explicitly reported zero, and omitted/unknown accounting. Report first and repeat separately. This observes cache behavior; it does not estimate a causal effect of enabling caching.

A causal cache-on/cache-off experiment would require a separately authorized project configuration change and another study. Random text at the front of a prompt is not proof that the provider cache was bypassed.

## Budget and stopping

Authority: the user approved up to **US$20 of model inference** on a named existing GCP project on 2026-09-21, before any study inference. The project identifier stays out of public evidence. No inference is part of offline validation. The runner requires `--execute`, `--project`, `--max-usd` (at most 20), a verified server binary, and a new output directory.

The [Google price table](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing), checked on 2026-09-21, lists global Gemini 3.8 Flash introductory rates of $0.75/M input and $3.75/M output including reasoning, through 2026-12-31. The local budget deliberately charges all reported tokens at $3.75/M, ignoring cache discounts. Before every inference, `count_tokens` measures the input with the same system instruction and tools; the runner reserves the higher rate for that count plus 10%, 4,096 framing tokens, and the 2,048 output limit. Input counts above 40,000 are rejected. Returned complete usage settles the reservation; failed requests or missing usage retain it. The continuation stops after three consecutive unreported inference requests. A reservation that exceeds the remaining budget stops the study.

This is a conservative local estimate, not a provider-enforced invoice cap. It excludes taxes, unrelated project spending, and any future pricing change. Recheck pricing before executing after the declared date. Token-counting preflight is included in recorded wall time, so these times must not be compared directly with the original runner's latency.

Each trial is limited to eight model turns and approximately 120 seconds, with 45-second inference, 20-second token-counting, and 20-second MCP call timeouts. Record every planned trial, including failures and unrun work. Stop on authentication/configuration errors, three consecutive unreported inference requests, budget exhaustion, or source drift. No retry-to-success loop. A full timeout-heavy schedule would take at most roughly two hours; budget and usage rules can stop it much earlier.

## Analysis and decision rule

Quality comes first. Report pass counts out of three per case, strategy, and pass, including all failures. Token medians are conditional on successful trials with complete usage, with their sample sizes. Compare strategies only within matched case/block/pass triplets where all three answers pass and usage is complete. Record cumulative and peak native input, reported total tokens, cache observations, model responses, discovery calls, blocked calls, and elapsed time separately.

For each candidate, return `useful_for_these_cases` only if all 54 planned trials pass with complete usage and that candidate uses fewer cumulative input tokens than eager in every matched triplet. Otherwise return `inconclusive_or_mixed`. Retain the per-case comparisons, not just an overall percentage. Three repetitions of three tasks do not become 54 independent observations: this small descriptive study does not establish population reliability, confidence intervals, billing savings, or a general winner between discovery and fixed filtering.

## Commands

Offline validation, no credentials or inference:

```bash
uv run --python 3.13.5 --script task/study.py
uv run --no-project --python 3.13.5 --with google-genai==2.24.0 --with mcp==2.2.0 \
  --with jsonschema==4.26.0 python -m unittest discover -s task -p 'test_*.py'
```

Authorized execution:

```bash
uv run --python 3.13.5 --script task/study.py --execute \
  --project YOUR_GCP_PROJECT --max-usd 20 \
  --server /absolute/path/to/github-mcp-server \
  --output /absolute/path/to/new-study-results
python task/analyze_study.py /absolute/path/to/new-study-results
```

Keep new results separate from `task/results/`. Add an article claim only after inspecting the full results and their limits. Nothing in this plan authorizes publication.

Pre-trial amendment: increased the local limit from the initially proposed US$5 to the user-authorized US$20. Cases, ordering, model, grader, and stopping rules are unchanged.

## Operational amendment after interruption

The initial execution completed two successful eager trials for `source`, then the fixed strategy's first trial received HTTP 429. Its original stop rule retained 51 unrun trials. `study-results-initial/` preserves that run, its exact runner, and its original plan. No failed attempt is replaced.

The separately recorded continuation executes only those 51 unrun identities. It carries forward the first run's conservative spend reservations, adds a 15-second minimum between request-preflight starts, and stops after three consecutive inference requests without usable usage, rather than after one. It preserves all other declared conditions, including the deterministic grader and decision rule. The continuation records the previous run and trial hashes. This amendment responds to infrastructure failure after partial case exposure; the cases were held out at initial freeze, not unseen at the time of this amendment. No prompt, search, answer, or grading change follows the observed answers.

The continuation used `--resume-from /absolute/path/to/study-results-initial` in addition to the authorized execution arguments above, with a new output directory. The corrected current runner refuses this historical continuation across its changed authority policy; see the post-run correction below. The combined descriptive report must identify the interruption and pacing change; it is not an uninterrupted preregistered run or a latency experiment.

## Post-run corrections for future execution

The run is finished and no further inference is authorized by this file itself. The current runner accepts `sha` as an alternative spelling of the same permitted commit, while rejecting conflicting or different references. The original task runner likewise rejects a different SHA overriding an allowed ref. These corrections were made after the observed strict-gate failure; the executed code, failed grade, and all source/usage observations remain archived unchanged. No new model trials or retrospective regrading were performed.

The current authority policy is `pinned-ref-or-sha-v2`. Resume is allowed only from that same policy revision; current code refuses to continue either historical run across this boundary change. To inspect or reproduce the old behavior, use its archived sources with the retained data, not the corrected current runner. Reusing these now-exposed cases is a replication or development exercise, not a fresh held-out evaluation.
