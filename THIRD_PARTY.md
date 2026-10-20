# Third-party material

The repository's MIT license applies to original benchmark code and documentation. Captured observations retain their upstream attribution; their presence is evidence of the inspected software, not an endorsement.

- GitHub MCP server v2.0.2: [source](https://github.com/github/github-mcp-server/tree/v2.0.2), MIT license reproduced in `licenses/github-mcp-server.txt`. The repository keeps catalogue and result sizes and digests, the framework-serialized tool declarations under `results/declarations/`, and a short quoted declaration from `pkg/github/tools.go` at commit `85598ba6e1256f7ebf4867b95d63b833c4549264` as the answer key. The server binary is not redistributed.
- GitHub issue [#2275](https://github.com/github/github-mcp-server/issues/2275) and release [v1.12.2](https://github.com/github/github-mcp-server/releases/tag/v1.12.2): only titles, states, dates, names, and logins needed by the answer key. User-authored bodies are not redistributed; run records keep the agents' answers, their shell commands, and sizes of what they read. A few shell commands embed excerpts of the MIT-licensed `tools.go`.
- The `gh` skill in `bench/skills/gh/` is the author's own, from [fmind/dot](https://github.com/fmind/dot), under MIT.
- Google Sans: the bundled regular font is distributed under the SIL Open Font License in `assets/fonts/GoogleSans-OFL.txt`.
- Claude Code, Codex CLI, Antigravity CLI, LangChain/LangGraph, Google ADK, and PydanticAI are measured as installed; their notices continue to apply. This repository does not redistribute their binaries or packages.

The September 2026 edition's third-party notices, including the Codex model fixture, remain with that edition in the repository history.
