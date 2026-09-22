# ruff: noqa: PT009, PT027
# Standard-library unittest keeps validation independent of pytest.
"""Offline regression checks for the follow-up study's evidence boundaries."""

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from analyze_study import analyze
from google.genai import types
from study import FIXED, Budget, BudgetExceededError, allowed, grade, initial_tools, schedule, trial, validate_cases

ROOT = Path(__file__).parent
CASES = json.loads((ROOT / "study-cases.json").read_text())["cases"]
RAW = json.loads((ROOT.parent / "data/github-default.json").read_text())["tools"]
CATALOG = {t["name"]: {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]} for t in RAW}


class StudyTests(unittest.TestCase):
    def test_fixture_and_fair_schedule(self):
        validate_cases(CASES, CATALOG)
        jobs = schedule(CASES)
        self.assertEqual(len(jobs), 54)
        self.assertEqual(len({tuple(j.values()) for j in jobs}), 54)
        for case in CASES:
            orders = [
                [j["mode"] for j in jobs if j["case"] == case["id"] and j["block"] == b and j["phase"] == "first"]
                for b in range(3)
            ]
            for position in range(3):
                self.assertEqual({order[position] for order in orders}, {"eager", "fixed", "discovery"})

    def test_fixed_role_is_constant_and_independent_of_case(self):
        self.assertEqual(set(initial_tools("fixed", CATALOG)), set(FIXED))
        self.assertEqual(len(initial_tools("eager", CATALOG)), 45)
        self.assertFalse(initial_tools("discovery", CATALOG))

    def test_grader_requires_evidence_types_and_scope(self):
        for case in CASES:
            answer = json.dumps(case["expected"])
            reads = [{"name": case["tool"], "ok": True}]
            self.assertTrue(grade(answer, reads, case)["passed"])
            self.assertFalse(grade(answer, [], case)["passed"])
            self.assertFalse(grade(f"```json\n{answer}\n```", reads, case)["passed"])
            self.assertFalse(grade(answer, [*reads, {"name": "issue_write", "blocked": True}], case)["passed"])
            changed = dict(case["expected"])
            field = next(iter(changed))
            changed[field] = None
            self.assertFalse(grade(json.dumps(changed), reads, case)["passed"])
        release = CASES[2]
        answer = dict(release["expected"], prerelease=0)
        self.assertFalse(grade(json.dumps(answer), [{"name": release["tool"], "ok": True}], release)["passed"])

    def test_authority_rejects_other_identifiers_and_extra_arguments(self):
        for case in CASES:
            self.assertTrue(allowed(case, case["tool"], case["arguments"]))
            self.assertFalse(allowed(case, "issue_write", case["arguments"]))
            self.assertFalse(allowed(case, case["tool"], dict(case["arguments"], owner="elsewhere")))
            self.assertFalse(allowed(case, case["tool"], dict(case["arguments"], unexpected=True)))

    def test_source_alias_preserves_pin_and_rejects_overrides(self):
        case = CASES[0]
        alias = dict(case["arguments"])
        alias["sha"] = alias.pop("ref")
        self.assertTrue(allowed(case, case["tool"], alias))
        self.assertTrue(allowed(case, case["tool"], dict(alias, ref=alias["sha"])))
        self.assertFalse(allowed(case, case["tool"], dict(case["arguments"], sha="main")))
        self.assertFalse(allowed(case, case["tool"], dict(alias, ref="main")))
        self.assertFalse(allowed(CASES[1], case["tool"], alias))

    def test_budget_preserves_unknown_usage_and_refuses_overrun(self):
        budget = Budget(0.1)
        reserved = budget.reserve(1000)
        budget.settle(reserved, {})
        self.assertEqual(budget.charged, reserved)
        self.assertEqual(budget.unreported_requests, 1)
        with self.assertRaises(BudgetExceededError):
            budget.reserve(40000)
        self.assertEqual(budget.charged, reserved)
        budget = Budget(5)
        reserved = budget.reserve(10000)
        budget.settle(reserved, {"prompt_token_count": 10000, "total_token_count": 11000})
        self.assertAlmostEqual(budget.charged, 11000 * 3.75 / 1_000_000)

    def test_analyzer_keeps_missing_usage_and_cache_unknown(self):
        records = [
            {
                **job,
                "grade": {"passed": True},
                "turns": [
                    {"usage": {"prompt_token_count": 100 if job["mode"] == "eager" else 50, "total_token_count": 110}}
                ],
            }
            for job in schedule(CASES)
        ]
        summary = analyze(records, CASES)
        self.assertEqual(summary["verdicts"]["fixed"], "useful_for_these_cases")
        self.assertEqual(len(summary["complete_matched_triplets"]), 18)
        self.assertEqual(summary["rows"][0]["cache_observation"], "unknown")
        broken = copy.deepcopy(records)
        broken[0]["turns"][0]["usage"] = {}
        self.assertEqual(analyze(broken, CASES)["verdicts"]["fixed"], "inconclusive_or_mixed")
        self.assertEqual(analyze(records[:-1], CASES)["missing"], 1)
        with self.assertRaises(ValueError):
            analyze([*records, records[0]], CASES)


class TrialTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_strategies_complete_a_read_and_preserve_model_state(self):
        case = CASES[0]
        usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=100, total_token_count=120)

        def response(part):
            return types.GenerateContentResponse(
                model_version="test",
                usage_metadata=usage,
                candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))],
            )

        for mode in ("eager", "fixed", "discovery"):
            replies = []
            if mode == "discovery":
                replies.append(
                    response(types.Part.from_function_call(name="search_tools", args={"query": "file contents"}))
                )
            replies.extend(
                [
                    response(types.Part.from_function_call(name=case["tool"], args=case["arguments"])),
                    response(types.Part.from_text(text=json.dumps(case["expected"]))),
                ]
            )
            generate = AsyncMock(side_effect=replies)
            counter = AsyncMock(return_value=SimpleNamespace(total_tokens=100))
            client = SimpleNamespace(
                aio=SimpleNamespace(models=SimpleNamespace(count_tokens=counter, generate_content=generate))
            )
            with patch("study.read_observation", new=AsyncMock(return_value=case["observation"])) as read:
                result = await trial(client, AsyncMock(), CATALOG, case, mode, 0, "first", Budget(5))
            self.assertTrue(result["grade"]["passed"], result)
            self.assertIsNone(result["error"])
            self.assertEqual(read.await_count, 1)
            self.assertEqual(len(result["turns"]), 3 if mode == "discovery" else 2)
            self.assertIn(case["tool"], result["turns"][-1]["declared_tools"])
            self.assertEqual(counter.await_count, generate.await_count)

    async def test_source_drift_stops_without_a_followup_inference(self):
        case = CASES[0]
        response = types.GenerateContentResponse(
            model_version="test",
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100, total_token_count=120),
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model", parts=[types.Part.from_function_call(name=case["tool"], args=case["arguments"])]
                    )
                )
            ],
        )
        generate = AsyncMock(return_value=response)
        client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    count_tokens=AsyncMock(return_value=SimpleNamespace(total_tokens=100)), generate_content=generate
                )
            )
        )
        with patch("study.read_observation", new=AsyncMock(return_value={"changed": True})):
            result = await trial(client, AsyncMock(), CATALOG, case, "fixed", 0, "first", Budget(5))
        self.assertEqual(result["error"], "source_drift")
        self.assertEqual(generate.await_count, 1)
        self.assertFalse(result["grade"]["passed"])

    async def test_missing_usage_stops_before_second_paid_request(self):
        generate = AsyncMock(return_value=SimpleNamespace(usage_metadata=None, model_version="test"))
        client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    count_tokens=AsyncMock(return_value=SimpleNamespace(total_tokens=1000)), generate_content=generate
                )
            )
        )
        budget = Budget(5)
        result = await trial(client, AsyncMock(), CATALOG, CASES[0], "eager", 0, "first", budget)
        self.assertEqual(generate.await_count, 1)
        self.assertEqual(result["error"], "incomplete_usage")
        self.assertGreater(budget.charged, 0)

    async def test_model_cannot_execute_a_visible_write(self):
        content = types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="issue_write",
                    args={"method": "create", "owner": "github", "repo": "github-mcp-server", "title": "No"},
                )
            ],
        )
        response = types.GenerateContentResponse(
            model_version="test",
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100, total_token_count=120),
            candidates=[types.Candidate(content=content)],
        )
        final = types.GenerateContentResponse(
            model_version="test",
            usage_metadata=response.usage_metadata,
            candidates=[
                types.Candidate(
                    content=types.Content(
                        role="model", parts=[types.Part.from_text(text=json.dumps(CASES[0]["expected"]))]
                    )
                )
            ],
        )
        client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    count_tokens=AsyncMock(return_value=SimpleNamespace(total_tokens=100)),
                    generate_content=AsyncMock(side_effect=[response, final]),
                )
            )
        )
        session = AsyncMock()
        result = await trial(client, session, CATALOG, CASES[0], "eager", 0, "first", Budget(5))
        session.call_tool.assert_not_awaited()
        self.assertTrue(result["calls"][0]["blocked"])
        self.assertFalse(result["grade"]["passed"])


if __name__ == "__main__":
    unittest.main()
