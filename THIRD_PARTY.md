# Third-party material

The repository's MIT license applies to original benchmark code and documentation. Captured tool definitions and public source observations retain their upstream attribution; their presence is evidence of the inspected software, not an endorsement.

- GitHub MCP server v1.12.2: [source](https://github.com/github/github-mcp-server/tree/v1.12.2), MIT license reproduced in `licenses/github-mcp-server.txt`. This includes its captured tool definitions and the `pkg/github/tools.go` and `go.mod` fixtures at commit `85598ba6e1256f7ebf4867b95d63b833c4549264`.
- GitHub issue [#2275](https://github.com/github/github-mcp-server/issues/2275): title and state retained with its URL, a short paraphrase, and a body digest. The complete user-authored issue body and user metadata are not redistributed.
- Follow-up GitHub observations: issue [#2250](https://github.com/github/github-mcp-server/issues/2250) contributes only its number, title, state, and URL. Release [v1.12.2](https://github.com/github/github-mcp-server/releases/tag/v1.12.2) contributes tag/date/status and asset names, byte sizes, and digests. User-authored bodies and author metadata are not redistributed.
- Codex model capability fixture: extracted from the [rust-v0.154.0 model catalogue](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/models-manager/models.json), Copyright OpenAI, distributed under Apache-2.0 in `licenses/codex.txt`, with the upstream notices in `licenses/codex-NOTICE.txt`. The benchmark replaces `base_instructions` with its own fixed instruction and sets `model_messages` to null. This is a new control, not a copy of the unretained original account cache.
- Google Sans: the bundled regular font is distributed under the SIL Open Font License in `assets/fonts/GoogleSans-OFL.txt`.
- Claude Code, Codex, goose, LangChain, Google ADK, CrewAI, and PydanticAI tool declarations are retained only as the measurement inputs identified in `METHODS.md` and `data/environment.json`; their respective project/product notices continue to apply. This repository does not redistribute their binaries or claim ownership of those descriptions.

The body of the accompanying article and unrelated files from the author's publishing workspace are not part of this repository.
