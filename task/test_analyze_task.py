# ruff: noqa: PT009
"""Failed or partial requests must not masquerade as cheap completed tasks."""

import unittest

from analyze_task import summarize


def observation(pair: int, mode: str, tokens: int, error: str | None = None) -> dict:
    return {
        "pair": pair,
        "mode": mode,
        "turns": [{"usage": {"prompt_token_count": tokens, "total_token_count": tokens + 10}}],
        "calls": [],
        "wall_seconds": 1,
        "error": error,
        "grade": {"passed": error is None},
    }


class SummaryTests(unittest.TestCase):
    def test_partial_usage_is_retained_but_excluded_from_medians(self) -> None:
        summary, rows = summarize(
            [
                observation(0, "eager", 100),
                observation(1, "eager", 1, "provider_429"),
            ]
        )
        self.assertEqual(summary["eager"]["median_input_tokens"], 100)
        self.assertEqual(summary["eager"]["median_sample_size"], 1)
        self.assertEqual(rows[1]["input_tokens"], 1)
        self.assertFalse(rows[1]["usage_complete"])
        self.assertEqual(summary["verdict"], "inconclusive_or_mixed")

    def test_missing_usage_cannot_form_a_completed_pair(self) -> None:
        summary, rows = summarize(
            [
                observation(0, "discovery", 50),
                {"pair": 0, "mode": "eager", "status": "not_run", "reason": "token_budget"},
            ]
        )
        self.assertEqual(summary["paired"], [])
        self.assertIsNone(summary["eager"]["median_input_tokens"])
        self.assertFalse(rows[1]["usage_complete"])

    def test_declared_decision_requires_five_successful_pairs(self) -> None:
        trials = [
            observation(i, mode, 100 if mode == "eager" else 50) for i in range(5) for mode in ["eager", "discovery"]
        ]
        summary, _ = summarize(trials)
        self.assertEqual(summary["verdict"], "useful_for_this_case")
        self.assertEqual(len(summary["paired"]), 5)
        self.assertEqual(summary["paired"][0]["input_reduction_percent"], 50)


if __name__ == "__main__":
    unittest.main()
