# ruff: noqa: PT009
"""Failed or partial requests must not masquerade as cheap completed tasks."""

import json
import unittest
from pathlib import Path

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
    def test_missing_or_invalid_usage_cannot_win_even_with_passing_grades(self) -> None:
        invalid = [
            {},
            {"total_token_count": 110},
            {"prompt_token_count": 100},
            {"prompt_token_count": None, "total_token_count": 110},
            {"prompt_token_count": "100", "total_token_count": 110},
            {"prompt_token_count": True, "total_token_count": 110},
            {"prompt_token_count": -1, "total_token_count": 110},
            {"prompt_token_count": 0, "total_token_count": 110},
            {"prompt_token_count": 100, "total_token_count": 0},
            {"prompt_token_count": 100, "total_token_count": 50},
            {"prompt_token_count": 100, "total_token_count": 110, "cached_content_token_count": 101},
            {"prompt_token_count": 100, "total_token_count": 110, "candidates_token_count": None},
        ]
        for usage in invalid:
            for bad_mode in ["eager", "discovery"]:
                with self.subTest(usage=usage, mode=bad_mode):
                    trials = [
                        observation(pair, mode, 100 if mode == "eager" else 50)
                        for pair in range(5)
                        for mode in ["eager", "discovery"]
                    ]
                    for trial in trials:
                        if trial["mode"] == bad_mode:
                            trial["turns"][0]["usage"] = usage
                    summary, rows = summarize(trials)
                    self.assertEqual(summary["paired"], [])
                    self.assertEqual(summary["verdict"], "inconclusive_or_mixed")
                    self.assertEqual(summary[bad_mode]["median_sample_size"], 0)
                    self.assertFalse(any(row["usage_complete"] for row in rows if row["mode"] == bad_mode))

    def test_one_missing_response_preserves_other_usage_but_excludes_trial(self) -> None:
        trial = observation(0, "discovery", 50)
        trial["turns"].append({})
        summary, rows = summarize([observation(0, "eager", 100), trial])
        self.assertEqual(rows[1]["input_tokens"], 50)
        self.assertFalse(rows[1]["usage_complete"])
        self.assertEqual(summary["paired"], [])

    def test_passing_grade_does_not_override_incomplete_provider_request(self) -> None:
        trial = observation(0, "discovery", 50, "provider_429")
        trial["grade"]["passed"] = True
        summary, _ = summarize([observation(0, "eager", 100), trial])
        self.assertEqual(summary["paired"], [])

    def test_retained_results_are_unchanged(self) -> None:
        root = Path(__file__).parent / "results"
        summary, _ = summarize(json.loads((root / "trials.json").read_text()))
        self.assertEqual(summary, json.loads((root / "summary.json").read_text()))

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
