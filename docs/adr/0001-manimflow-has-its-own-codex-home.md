# ManimFlow has its own Codex home

ManimFlow starts the Codex app-server with `CODEX_HOME` set to a folder it owns, instead of sharing `~/.codex` with any Codex the teacher installed:

- Windows: `%LOCALAPPDATA%\ManimFlow\codex`
- macOS: `~/Library/Application Support/ManimFlow/codex`
- Linux: `$XDG_DATA_HOME/ManimFlow/codex`, which defaults to `~/.local/share/ManimFlow/codex`

## Why

Codex reads more than credentials from its home. `config.toml` can change the model provider, the sandbox, approval rules and MCP servers. A global `AGENTS.md` adds instructions to every thread. Skills and memories add their own context. ManimFlow's guarantees (writes only inside the lesson, no network, the base instructions) must not depend on what a separate Codex install has set up for other work. A teacher who also uses the Codex CLI might allow network access there, or give it instructions that make no sense in a lesson.

Credentials stay separate too. Signing out of ManimFlow does not sign the teacher out of their own Codex, and the reverse is also true. The login is stored in this home's `auth.json`, so it survives restarts.

## Consequences

- A teacher who already uses Codex signs in once more, inside ManimFlow.
- Past threads live in ManimFlow's home, which is where the session list will read them.
- Tests point Codex at a local mock model by writing a `config.toml` into a temporary home, with no extra test-only setting in the adapter.
