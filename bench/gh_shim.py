#!/usr/bin/env python3
"""Read-only `gh` shim installed first on PATH for one benchmark run.

The runner copies this file as `gh` and replaces the four constants below. In MCP
conditions it refuses every command, so GitHub is reachable only through the server.
In the CLI condition it forwards read commands to the real `gh` and logs each argv and
output size, never the output text.
"""

import json
import os
import subprocess
import sys
import time

MODE = "__MODE__"
LOG = "__LOG__"
REAL_GH = "__REAL_GH__"
REAL_HOME = "__REAL_HOME__"

READ_COMMANDS = {
    ("issue", "view"),
    ("issue", "list"),
    ("pr", "view"),
    ("pr", "list"),
    ("pr", "diff"),
    ("release", "view"),
    ("release", "list"),
    ("repo", "view"),
    ("search", "code"),
    ("search", "issues"),
    ("search", "prs"),
    ("search", "repos"),
    ("search", "commits"),
}
WRITE_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}


def verdict(args: list[str]) -> str | None:
    if MODE != "read":
        return "gh is disabled in this benchmark condition; use the GitHub MCP tools."
    words = [a for a in args if not a.startswith("-")]
    if not words or args[0] in {"--help", "-h", "help", "--version", "version"} or "--help" in args:
        return None
    if tuple(words[:2]) in READ_COMMANDS:
        return None
    if words[0] == "api":
        method = None
        for i, arg in enumerate(args):
            if arg in {"-X", "--method"} and i + 1 < len(args):
                method = args[i + 1].upper()
            elif arg.startswith(("--method=", "-X=")):
                method = arg.split("=", 1)[1].upper()
            elif arg.startswith("-X"):  # compact form: -XPOST
                method = arg[2:].upper()
        fields = any(
            a in WRITE_FLAGS
            or a.startswith(("--field=", "--raw-field=", "--input="))
            or (len(a) > 2 and a[:2] in {"-f", "-F"})  # compact form: -ftitle=x
            for a in args
        )
        if method is None and fields:
            return "gh api with fields defaults to POST; pass --method GET for reads."
        return None if method in {None, "GET"} else "Only GET requests are allowed in this benchmark."
    return "Only read-only gh commands are allowed in this benchmark."


def main() -> int:
    args = sys.argv[1:]
    reason = verdict(args)
    entry = {"event": "gh", "argv": args, "started": time.time()}
    if reason:
        sys.stderr.write(reason + "\n")
        entry.update(ok=False, blocked=True)
        code = 1
    else:
        result = subprocess.run(
            [REAL_GH, *args],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "HOME": REAL_HOME,
                "GH_CONFIG_DIR": os.path.join(REAL_HOME, ".config", "gh"),
                "GH_PROMPT_DISABLED": "1",
                "NO_COLOR": "1",
            },
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        entry.update(ok=result.returncode == 0, stdout_chars=len(result.stdout), stderr_chars=len(result.stderr))
        code = result.returncode
    try:
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
