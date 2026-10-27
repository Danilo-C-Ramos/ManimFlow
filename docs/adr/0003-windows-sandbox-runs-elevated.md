# The Windows sandbox runs elevated, and waits for Codex's read grants

On Windows, ManimFlow sets up Codex's sandbox in the elevated mode, which asks once for administrator. When the teacher declines, or isn't an administrator, it falls back to the unelevated mode. Before the agent's first turn, it runs one command through the sandbox and waits until Codex has finished granting the sandbox read access to the teacher's folders.

## Why

A Windows CI probe (Codex 0.162.1, windows-latest) showed:

- **Only the elevated mode cuts the network.** In the unelevated mode the agent reaches the internet. In the elevated mode, connections out fail with `WinError 10013`, but loopback still works. Both modes keep writes inside the lesson.
- **The temp folder is off limits.** With the lesson under `%TEMP%`, every command starts in `C:\` (elevated) or `C:\Program Files\PowerShell\7` (unelevated), so writes and `manimflow` fail. Under `Documents`, `AppData\Local` or another drive, both modes work. This is why the example lesson is now copied to ManimFlow's own folder (`%LOCALAPPDATA%\ManimFlow\exemplo`) and not to a temp folder, and why the tests move their lessons out of `tmp_path` on Windows.
- **The read grants happen after the first command starts.** In the elevated mode, each command first runs a setup refresh. The refresh starts a helper that grants the sandbox users read access to each folder in the user profile, and holds the `Local\CodexSandboxReadAcl` mutex while it works. Codex doesn't wait for it. While the helper runs, commands get a working directory through a junction that the sandbox user can't create, and start in `C:\`. On a CI runner the helper outlasts a whole turn. Once it has run, later refreshes find the grants in place.
- **Setup persists.** The setup writes `[windows] sandbox = "elevated"` (or `"unelevated"`) to `config.toml` in ManimFlow's Codex home. From the next start on, readiness reports `ready`, so the administrator prompt shows only once.

## Consequences

- The sandbox is prepared in the background, so the first page and the sign-in don't wait for the administrator prompt or the read grants. Opening the chat waits instead, because a Codex thread takes the sandbox config when it starts and blocks every command until setup ends. The first time, on a large profile, that wait can last minutes.
- A teacher without administrator rights gets an agent that writes only inside the lesson but can reach the network. ManimFlow only logs this.
- The network test skips loopback on Windows and checks an internet address instead, skipping when the machine itself has no internet.
- Waiting on the mutex depends on a Codex internal. If Codex renames it, the wait ends at once and the first commands may start in `C:\` again. The Windows CI catches that.
