# Interrupted initial execution

The initial study executed three planned identities: two eager successes on the source case, then one fixed-strategy HTTP 429 failure. Its declared stop rule left 51 trials unrun. None was replaced. See `summary.json` for the complete schedule, including unrun entries, and `run.json` for versions, hashes, and conservative budget accounting.

`STUDY.md` and the Python files preserve the plan and runner used at that point. They are historical inspection copies; execute from the repository's `task/` directory with its sibling `data/` when reproducing the environment. The separately declared continuation is documented in [the current study plan](../STUDY.md). Preserve these initial observations when interpreting any combined report.
