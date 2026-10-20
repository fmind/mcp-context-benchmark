"""Offline tests for the read-only controls, audits, grading, and schedule. No model, no network."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import common
import study

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("gh_shim", HERE / "gh_shim.py")
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)


class ShimTest(unittest.TestCase):
    def test_off_mode_refuses_everything(self) -> None:
        shim.MODE = "off"
        self.assertIsNotNone(shim.verdict(["issue", "view", "1"]))

    def test_read_mode_allows_reads_and_rejects_writes(self) -> None:
        shim.MODE = "read"
        self.assertIsNone(shim.verdict(["issue", "view", "2275", "-R", "github/github-mcp-server"]))
        self.assertIsNone(shim.verdict(["release", "view", "v1.12.2", "--json", "tagName"]))
        self.assertIsNone(shim.verdict(["api", "repos/o/r/contents/x", "--jq", ".content"]))
        self.assertIsNone(shim.verdict(["api", "--method", "GET", "search/issues", "-f", "q=x"]))
        self.assertIsNotNone(shim.verdict(["api", "repos/o/r/issues", "-f", "title=x"]))
        self.assertIsNotNone(shim.verdict(["api", "-X", "DELETE", "repos/o/r"]))
        self.assertIsNotNone(shim.verdict(["api", "-XPOST", "repos/o/r/issues/1/lock"]))
        self.assertIsNotNone(shim.verdict(["api", "repos/o/r/issues", "-ftitle=x"]))
        self.assertIsNotNone(shim.verdict(["api", "repos/o/r/issues", "-Ftitle=x"]))
        self.assertIsNone(shim.verdict(["api", "-XGET", "repos/o/r"]))
        self.assertIsNotNone(shim.verdict(["issue", "create", "--title", "x"]))
        self.assertIsNotNone(shim.verdict(["repo", "delete", "o/r"]))


class GateTest(unittest.TestCase):
    def test_gate_blocks_writes_and_logs_versions(self) -> None:
        """Run the gate against a fake stdio server that echoes a catalogue and tool results."""
        fake = (
            "import json,sys\n"
            "for line in sys.stdin:\n"
            "    m = json.loads(line)\n"
            "    if 'id' not in m: continue\n"
            "    r = {'tools': [{'name': 'issue_read', 'outputSchema': {}}, {'name': 'issue_write'}]} if m['method'] == 'tools/list' "
            "else {'content': [{'type': 'text', 'text': 'abc'}]}\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'id': m['id'], 'result': r}), flush=True)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            server, gh, log = Path(tmp) / "server.py", Path(tmp) / "gh", Path(tmp) / "gate.jsonl"
            server.write_text(fake)
            gh.write_text("#!/bin/sh\necho token\n")
            gh.chmod(0o755)
            wrapper = Path(tmp) / "server"
            wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {server}\n")
            wrapper.chmod(0o755)
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "issue_write", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "issue_read", "arguments": {}}},
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {"name": "issue_write", "arguments": {}},
                    }
                ],
            ]
            out = subprocess.run(
                [sys.executable, str(HERE / "gate.py"), str(log), str(gh), tmp, str(wrapper)],
                input="".join(json.dumps(m) + "\n" for m in messages), capture_output=True, text=True, timeout=30,
                check=True,
            ).stdout  # fmt: skip
            replies = {r["id"]: r for r in map(json.loads, out.splitlines())}
            self.assertTrue(replies[3]["result"]["isError"])
            self.assertEqual(replies[None]["error"]["code"], -32600)
            self.assertNotIn(5, replies)
            entries = common.read_jsonl(log)
        self.assertIn({"event": "initialize", "protocol_version": "2025-11-25"}, entries)
        listed = next(e for e in entries if e["event"] == "tools/list:result")
        self.assertEqual((listed["count"], listed["output_schemas"]), (2, 1))
        calls = [e for e in entries if e["event"] == "tools/call"]
        self.assertEqual(
            [(c["name"], c.get("blocked", False), c["ok"]) for c in calls],
            [("issue_write", True, False), ("issue_read", False, True)],
        )
        self.assertIn({"event": "batch", "ok": False, "blocked": True}, entries)


class AuditTest(unittest.TestCase):
    def test_network_bypass_ignores_gh_segments(self) -> None:
        commands = ["gh api repos/o/r/contents/x | grep -n y", "curl -s https://raw.githubusercontent.com/o/r/x"]
        self.assertEqual(common.bypasses(commands), commands[1:])
        sneaky = [
            "~/.local/share/mise/installs/gh/bin/gh api -X POST x",
            "mise exec gh -- gh issue close 1",
            "git -C work fetch origin",
            "cat skills/gh/SKILL.md",
            "ls .claude/skills/gh",
        ]
        self.assertEqual(common.bypasses(sneaky), sneaky[:3])

    def test_outside_paths_allow_own_run_and_host_state(self) -> None:
        own = common.REAL_HOME / "runs" / "a"
        stream = " ".join(
            [
                str(own / "work" / "x"),
                str(common.REAL_HOME / ".gemini" / "antigravity-cli" / "mcp" / "github" / "issue_read.json"),
                str(common.REAL_HOME / "project" / "bench" / "common.py"),
            ]
        )
        self.assertEqual(common.outside_paths(stream, own), [str(common.REAL_HOME / "project" / "bench" / "common.py")])

    def test_outside_paths_catch_home_shorthands_climbs_and_other_conversations(self) -> None:
        own = common.REAL_HOME / "runs" / "a"
        self.assertEqual(common.outside_paths("cat ~/.ssh/config", own), [str(common.REAL_HOME / ".ssh" / "config")])
        self.assertEqual(common.outside_paths("cat $HOME/notes", own), [str(common.REAL_HOME / "notes")])
        self.assertEqual(common.outside_paths("cat ../../rep2/record.json", own), ["../../rep2/record.json"])
        one = f"grep x {common.BRAIN}c1/steps/8/output.txt; cat ~/.gemini/antigravity-cli/brain/c1/steps/9/output.txt"
        self.assertEqual(common.outside_paths(one, own), [])
        two = f"{one} {common.BRAIN}c2/steps/3/output.txt"
        self.assertEqual(len(common.outside_paths(two, own)), 3)


class GradeTest(unittest.TestCase):
    def test_release_answer_passes_with_evidence(self) -> None:
        final = "```json\n" + json.dumps(common.EXPECTED["release"]["facts"]) + "\n```"
        grade = common.grade("release", "default", final, [{"name": "get_release_by_tag", "ok": True}], [])
        self.assertTrue(grade["passed"])
        self.assertFalse(grade["strict_format"])

    def test_release_answer_needs_the_designated_interface(self) -> None:
        final = json.dumps(common.EXPECTED["release"]["facts"])
        grade = common.grade("release", "eager", final, [{"name": "list_releases", "ok": True}], [])
        self.assertEqual(grade["errors"], ["No successful get_release_by_tag call"])

    def test_outside_read_fails_a_correct_answer(self) -> None:
        final = json.dumps(common.EXPECTED["release"]["facts"])
        calls = [{"name": "get_release_by_tag", "ok": True}]
        self.assertFalse(common.grade("release", "default", final, calls, [], ["/elsewhere/common.py"])["passed"])

    def test_cli_issue_state_is_case_insensitive_and_citation_separate(self) -> None:
        answer = dict(common.EXPECTED["issue"]["facts"], issue_state="CLOSED", source_line_start=1)
        calls = [
            {"argv": ["issue", "view", "2275"], "ok": True},
            {"argv": ["api", "repos/o/r/contents/pkg/github/tools.go"], "ok": True},
        ]
        grade = common.grade("issue", "cli", json.dumps(answer), calls, [])
        self.assertTrue(grade["passed"], grade["errors"])
        self.assertFalse(grade["citation"])


class ScheduleTest(unittest.TestCase):
    def test_every_condition_runs_each_task_and_rotates(self) -> None:
        runs = study.schedule("adk")
        self.assertEqual(len(runs), 4 * 2 + 3 * 5 + 3 * 5)
        firsts = {
            runs_of[0][1] for runs_of in ([r for r in runs if r[0] == "issue" and r[2] == rep] for rep in (1, 2, 3))
        }
        self.assertEqual(len(firsts), 3)


if __name__ == "__main__":
    unittest.main()
