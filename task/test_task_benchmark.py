# ruff: noqa: PT009
# Standard-library unittest keeps offline validation independent of pytest.
"""Offline checks for grading, execution scope, and the complete discovery loop."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import task_benchmark as bench
from google.genai import types

FIXTURE = json.loads((Path(__file__).parent / "fixture.json").read_text())
CATALOG = {
    t["name"]: {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}
    for t in json.loads((Path(__file__).parents[1] / "data/github-default.json").read_text())["tools"]
}
GOOD_CALLS = [{"name": name, "ok": True} for name in ["issue_read", "get_file_contents"]]


def response(parts: list[types.Part]) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason="STOP")],
        model_version="offline-test-only",
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=5, total_token_count=15
        ),
    )


class GraderTests(unittest.TestCase):
    def test_correct_answer_and_whitespace(self) -> None:
        answer = dict(FIXTURE["expected"])
        answer["evidence_quote"] = answer["evidence_quote"].replace("\t", "  ")
        self.assertTrue(bench.grade(json.dumps(answer), GOOD_CALLS, FIXTURE["expected"])["passed"])

    def test_wrong_answer_and_missing_evidence_fail(self) -> None:
        for field, value in [
            ("default_enabled", True),
            ("source_line_start", 1),
            ("evidence_quote", "made up"),
            ("source_ref", "main"),
        ]:
            with self.subTest(field=field):
                answer = dict(FIXTURE["expected"], **{field: value})
                self.assertFalse(bench.grade(json.dumps(answer), GOOD_CALLS, FIXTURE["expected"])["passed"])
        self.assertFalse(bench.grade(json.dumps(FIXTURE["expected"]), [], FIXTURE["expected"])["passed"])
        self.assertFalse(
            bench.grade(
                json.dumps(FIXTURE["expected"]),
                [*GOOD_CALLS, {"name": "delete_repository", "blocked": True}],
                FIXTURE["expected"],
            )["passed"]
        )

    def test_source_alias_cannot_override_the_allowed_commit(self) -> None:
        args = {"owner": "github", "repo": "github-mcp-server", "path": bench.SOURCE}
        self.assertTrue(bench.allowed("get_file_contents", dict(args, sha=bench.REF)))
        self.assertTrue(bench.allowed("get_file_contents", dict(args, ref=bench.REF, sha=bench.REF)))
        self.assertFalse(bench.allowed("get_file_contents", dict(args, ref=bench.REF, sha="main")))
        self.assertFalse(bench.allowed("get_file_contents", dict(args, ref="main", sha=bench.REF)))
        self.assertFalse(bench.allowed("get_file_contents", args))

    def test_execution_scope(self) -> None:
        self.assertFalse(bench.allowed("delete_repository", {"owner": "github", "repo": "github-mcp-server"}))
        self.assertFalse(
            bench.allowed(
                "get_file_contents",
                {"owner": "github", "repo": "github-mcp-server", "path": bench.SOURCE, "ref": "main"},
            )
        )
        self.assertFalse(
            bench.allowed(
                "issue_read", {"owner": "different", "repo": "github-mcp-server", "method": "get", "issue_number": 2275}
            )
        )


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_loads_tools_then_reads_both_sources(self) -> None:
        generated = AsyncMock(
            side_effect=[
                response(
                    [
                        types.Part(
                            function_call=types.FunctionCall(
                                name="search_tools", args={"query": "issue read file contents"}
                            )
                        )
                    ]
                ),
                response(
                    [
                        types.Part(
                            function_call=types.FunctionCall(
                                name="issue_read",
                                args={
                                    "owner": "github",
                                    "repo": "github-mcp-server",
                                    "issue_number": 2275,
                                    "method": "get",
                                },
                            )
                        ),
                        types.Part(
                            function_call=types.FunctionCall(
                                name="get_file_contents",
                                args={
                                    "owner": "github",
                                    "repo": "github-mcp-server",
                                    "path": bench.SOURCE,
                                    "ref": bench.REF,
                                },
                            )
                        ),
                    ]
                ),
                response([types.Part.from_text(text=json.dumps(FIXTURE["expected"]))]),
            ]
        )
        client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generated)))
        budget = [100000]
        with patch.object(
            bench, "call", AsyncMock(side_effect=[FIXTURE["issue_read"], FIXTURE["get_file_contents"]])
        ) as call:
            result = await bench.trial(client, None, CATALOG, FIXTURE, "discovery", 0, budget)
        self.assertTrue(result["grade"]["passed"], result)
        self.assertEqual(call.await_count, 2)
        self.assertEqual(budget[0], 99955)
        self.assertEqual(result["turns"][0]["declared_tools"], ["search_tools"])
        self.assertIn("issue_read", result["turns"][1]["declared_tools"])
        self.assertIn("get_file_contents", result["turns"][1]["declared_tools"])

    async def test_write_is_blocked_before_mcp_dispatch(self) -> None:
        generated = AsyncMock(
            side_effect=[
                response(
                    [
                        types.Part(
                            function_call=types.FunctionCall(
                                name="create_branch",
                                args={"owner": "github", "repo": "github-mcp-server", "branch": "unwanted"},
                            )
                        )
                    ]
                ),
                response([types.Part.from_text(text="{}")]),
            ]
        )
        client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generated)))
        with patch.object(bench, "call", AsyncMock()) as call:
            result = await bench.trial(client, None, CATALOG, FIXTURE, "eager", 0, [100000])
        call.assert_not_called()
        self.assertFalse(result["grade"]["passed"])
        self.assertTrue(result["calls"][0]["blocked"])


if __name__ == "__main__":
    unittest.main()
