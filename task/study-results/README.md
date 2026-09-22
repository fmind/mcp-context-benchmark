# Three-strategy study results, 21 September 2026

**Verdict: inconclusive.** Of 54 planned trials, 21 were attempted: 13 passed, seven ended with provider errors (five HTTP 429, two HTTP 504), and one failed the exact argument gate despite a correct final answer. The remaining 33 were not run after the continuation reached its three-consecutive-provider-failure stop rule. No failed trial was replaced.

| Strategy | Passed | Attempted | Planned | Not run |
| --- | ---: | ---: | ---: | ---: |
| Eager | 5 | 6 | 18 | 12 |
| Fixed role allowlist | 4 | 8 | 18 | 10 |
| Discovery | 4 | 7 | 18 | 11 |

The unequal attempted counts reflect the interrupted schedule. Do not rank reliability by these fractions. All responses reporting a model version returned the alias `gemini-3.8-flash`, not an immutable backend revision.

## Complete matched comparisons

Only two of the 18 planned case/block/pass triplets completed with all three answers passing and complete native usage. Both are repeat passes in block zero. The source-file case has no complete matched triplet.

| Case | Eager input | Fixed input | Discovery input | Fixed reduction | Discovery reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Issue metadata, repeat | 17,177 | 1,391 | 2,010 | 91.9% | 88.3% |
| Release asset, repeat | 17,988 | 2,262 | 2,048 | 87.4% | 88.6% |

These are cumulative provider-native input tokens, including cached input and all discovery turns. Each fixed and eager trial used two model responses; each discovery trial used three. They are small retrieval tasks with supplied identifiers and projected results, not long investigations. The fixed role has three constant tools covering source, issue, and release inspection; it was not specialized separately for each answer. Its declarations count 708 `o200k_base` reference tokens, not the original startup subset's 989.

Caching remained provider-managed. First/repeat describes ordering, not cold/warm cache. Eager release retrieval reported 10,758 cached input tokens. Some responses omit cache fields; those totals remain unknown rather than being imputed as zero. No cache-controlled cost or latency comparison follows. Wall time includes token-counting preflight and, in the continuation, request pacing.

## Interruption and harness finding

The [initial execution](../study-results-initial/) stopped after two eager successes and a fixed-strategy HTTP 429 under its original stop rule. Before executing any remaining identity, [the operational amendment](STUDY.md#operational-amendment-after-interruption) added 15-second pacing and allowed up to three consecutive unreported inference requests. This report carries the initial three attempts unchanged and adds the 18 attempted continuation trials. `run.json` records the prior run/trial hashes and carried budget. The combined sequence is not an uninterrupted preregistered run.

One discovery trial used the supported `sha` argument for the correct pinned commit, then recovered with `ref` and returned the correct facts. The strict gate rejected the first spelling because it compared exact argument dictionaries. That was a harness limitation, not an unsafe write or an incorrect answer. The declared grade remains failed; no retrospective regrading occurred. A [separate no-inference verification](../../validation/github-reference-alias-2026-09-21.json) confirms that both spellings return identical projected source fixtures. Future runners accept the pinned alias and reject a conflicting or different SHA; their code is distinct from the exact executed copies retained here. No live trial has run with that fix.

## Trace and accounting

- [Every planned identity, response usage, tool call, answer, and grade](trials.json), including failed and unrun work.
- [Recomputed summary](summary.json), with per-case/strategy/pass counts and conditional medians.
- [Runtime identity](run.json): Python, every installed dependency, model settings, protocol, source hashes, UTC times, and budget accounting.
- [Frozen cases and source observations](study-cases.json); [executed plan](STUDY.md); [executed runner](study.py) and its captured helper modules.

Conservative model-spend accounting totals **US$0.64317675**, including the initial run and full reservations for seven requests that returned no usable usage. The authorized cap was US$20. This deliberately uses the higher output rate for every reported token and includes a reserve for unreported requests; it is not a verified invoice. It does not imply missing-usage requests were free.

Recompute the summary without inference from the repository root:

```bash
python task/analyze_study.py task/study-results
```

Retain both result directories. The 2026-09-21 source cases were held out at their initial freeze; after these attempts they are exposed cases for future development. No broader quality, latency, cost, or agent-product conclusion is established.
