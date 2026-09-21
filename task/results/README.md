# Observed GitHub task trials, 2026-09-21

**Verdict: inconclusive or mixed under the predeclared rule.** Eager and discovery each passed 2 of 5 planned attempts. Five attempts were interrupted by provider errors or a client timeout. One discovery response contained the correct facts and source quote inside Markdown fences, violating the JSON-only output contract. No trials were replaced and the grader was not relaxed.

GCP Agent Platform, `global`, `gemini-3.8-flash`, low thinking, Python 3.13.5. The provider returned the same model alias as its observed version. See [the frozen plan](../PLAN.md), [run identity and prompts](run.json), [source fixture](fixture.json), and [all responses, usage and tool calls](trials.json). Project identity and credentials are excluded. The runner's SHA-256 is recorded in `run.json`.

## Every attempt

Pair numbers here are one-based; machine records use zero-based indexes. Input is cumulative native `prompt_token_count` across returned responses, including cached input. A dash means the failed request supplied no usage, not that it was free.

| Pair | Strategy | Outcome | Reported input tokens | Wall seconds |
| --- | --- | --- | ---: | ---: |
| 1 | Eager | HTTP 429 before first response | - | 6.23 |
| 1 | Discovery | Pass | 14,080 | 15.64 |
| 2 | Discovery | HTTP 429 after two search turns | 1,311, partial | 23.34 |
| 2 | Eager | HTTP 504 before first response | - | 43.17 |
| 3 | Eager | Pass | 33,807 | 13.85 |
| 3 | Discovery | HTTP 429 before first response | - | 7.46 |
| 4 | Discovery | Correct facts, invalid output format | 11,228 | 19.86 |
| 4 | Eager | Client timeout before first response | - | 45.05 |
| 5 | Eager | Pass | 33,807 | 15.05 |
| 5 | Discovery | Pass | 14,067 | 13.62 |

The HTTP statuses establish request failures, not their root cause. The observations cannot attribute those failures to catalogue size. The failed-format answer successfully read both sources; removing its fences diagnostically yields all expected fields, but that is not an allowed repair in the declared grader.

## The one pair where both passed

| Metric | Eager | Discovery |
| --- | ---: | ---: |
| Cumulative input tokens | 33,807 | 14,067 |
| Maximum input in one request | 16,403 | 9,386 |
| Output tokens | 342 | 377 |
| Provider-reported total tokens | 34,149 | 14,444 |
| Cached input tokens, included above | 18,058 | 0 |
| Model requests returning responses | 3 | 5 |
| Discovery calls | 0 | 2 |
| Successful GitHub MCP reads | 2 | 2 |
| Wall seconds | 15.05 | 13.62 |

Discovery reduced cumulative input by 58.4% and reported total tokens by 57.7% in this pair, including search turns. It made two additional model requests. One pair cannot establish a stable latency improvement. The eager run benefited from cached input; token reductions are not an invoice saving estimate.

Both successful discovery trials loaded six GitHub definitions through two keyword searches before completing the two actual reads. Some matches were write-tool definitions; the independent execution boundary allowed only the two specified reads, and no trial attempted a write. The search is a small deterministic lexical ranker, not a model selector or a native coding-client search implementation. Its definitions remain loaded after discovery. Both conditions receive the same projected issue summary and complete numbered source file.

## Recompute and interpret

From the repository root:

```bash
python task/analyze_task.py task/results
```

This regenerates [summary.json](summary.json) and [trials.csv](trials.csv) without inference. Medians are explicitly conditional on successful completion, with only two observations per strategy. Partial usage is retained in CSV but excluded from those medians and from paired savings. Recorded total usage across returned trial responses is 110,144 tokens; failed requests can have unreported usage, and transport smoke tests are outside this total.

The five repeats use one development task, not independent task coverage. The task supplies a repository, issue number, file path, commit, and output contract. It does not test open-ended repository exploration. The source file is pinned and the issue observation hashed; future issue changes must not be silently combined with this run. Caching is provider-managed, sampling is stochastic, and no native client is evaluated end to end here.
