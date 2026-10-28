# ManimFlow

ManimFlow is a local app for teachers who want [Manim](https://www.manim.community/) animations for their slides without learning Manim. You describe the animation in Portuguese in a chat. An agent (OpenAI's Codex, signed in with your ChatGPT plan or an API key) writes the physics and the drawing as separate files. It renders previews, looks at the frames and fixes what it sees before it answers. Each lesson is a plain folder on your computer.

The interface is in Brazilian Portuguese. The code and these docs are in English.

ManimFlow is in early development. The 0.0.x releases prove that the install works on Windows. The home screen, the plan cards, the equations panel and export from the app are still being built. The `manimflow` command line already renders, checks continuity between states and exports.

## Install on Windows

Windows is the supported platform for v0.1. You need no administrator rights, and an existing Anaconda or Jupyter install stays as it is.

1. Install [uv](https://docs.astral.sh/uv/). In PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Close and reopen PowerShell so it finds `uv`.

2. Install LaTeX for ManimFlow. Manim needs it to write equations.

   ```powershell
   uvx manimflow doctor --install
   ```

   This downloads TinyTeX and the LaTeX packages Manim uses into `%LOCALAPPDATA%\ManimFlow\TinyTeX`. LaTeX breaks on folders with spaces or accents, so if your user name has one (`C:\Users\José da Silva`), TinyTeX goes into `%ProgramData%\ManimFlow\TinyTeX` instead, shared by every user of the computer. It takes a few minutes the first time. It then checks everything rendering needs and says in Portuguese what is still missing. Nothing changes in your PATH, so other programs don't see this LaTeX. Run `uvx manimflow doctor` later to check again.

3. Start ManimFlow:

   ```powershell
   uvx manimflow
   ```

`uvx` downloads ManimFlow and Python 3.12 into uv's own folder the first time, and reuses them after that.

## First run

`uvx manimflow` starts a local server on `127.0.0.1` and opens it in your browser. Nothing is reachable from other computers. Keep the PowerShell window open while you work; closing it stops ManimFlow.

1. Sign in. "Entrar com o ChatGPT" opens ChatGPT's login page and uses your Plus or Pro plan. If you don't have one, paste an OpenAI API key instead. ManimFlow keeps these credentials in its own folder, apart from any Codex you installed yourself.
2. The first time the agent runs, Windows may ask for administrator permission. That sets up the sandbox that keeps the agent inside the lesson folder and off the internet. You can decline. The agent then still writes only inside the lesson, but it can reach the internet.
3. The 0.0.x releases open the bundled example lesson, special relativity with a hero and a mirror, in `%LOCALAPPDATA%\ManimFlow\exemplo`. ManimFlow copies it fresh at every launch, so changes to it don't last.

To try the app without signing in, run `uvx manimflow --demo`. A scripted agent answers instead of Codex.

## Manual install steps

**A permanent `manimflow` command.** `uvx` is enough to use ManimFlow. If you'd rather type `manimflow` than `uvx manimflow`, install it as a uv tool:

```powershell
uv tool install manimflow
manimflow doctor --install
manimflow
```

Update with `uv tool upgrade manimflow`. With `uvx`, `uvx manimflow@latest` runs the newest release.

**Your own LaTeX.** If you already use MiKTeX or TeX Live, you can skip `doctor --install`. Run `uvx manimflow doctor`: it lists the LaTeX packages Manim needs that your distribution lacks. Install those with your distribution's package manager, such as MiKTeX Console, until `doctor` passes. See [docs/doctor.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/doctor.md) for the checks and the package list.

**Uninstall.** Run `uv tool uninstall manimflow` if you installed the tool, and `uv cache clean` to remove what `uvx` downloaded. Then delete `%LOCALAPPDATA%\ManimFlow`, which holds the sign-in, the example lesson copy and usually TinyTeX, and `%ProgramData%\ManimFlow` if TinyTeX went there. Your own lesson folders stay where they are.

## macOS and Linux

They are not officially supported in v0.1. [docs/install-macos-linux.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/install-macos-linux.md) describes a path through pixi and conda-forge.

## Development

You need [uv](https://docs.astral.sh/uv/) and git.

```bash
git clone https://github.com/Danilo-C-Ramos/ManimFlow.git
cd ManimFlow
uv sync
uv run manimflow doctor --install
uv run mypy
uv run pytest
```

On Linux, `uv sync` builds `pycairo` and `manimpango` from source, so install the cairo and pango headers first (`libcairo2-dev libpango1.0-dev pkg-config` on Debian and Ubuntu). On Ubuntu 23.10 and later, the agent's sandbox needs an AppArmor profile. `uv run manimflow doctor` prints the command that installs it.

`uv run pytest` skips the smoke test, which drives the real Codex agent and spends quota. Run it with `uv run pytest -m smoke` after signing in.

The design is in [docs/design.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/design.md), and the decisions behind it are in [docs/adr/](https://github.com/Danilo-C-Ramos/ManimFlow/tree/main/docs/adr).

### Releasing

The version comes from the git tag. Pushing a tag such as `v0.0.2` runs the release workflow. It runs the tests, builds the package, runs `uvx manimflow --help`, `doctor --install` and `doctor` from the built wheel on a clean Windows runner, and publishes to PyPI with trusted publishing. No token is stored in the repository.

```bash
git tag v0.0.2
git push origin v0.0.2
```

## License

MIT. See [LICENSE](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/LICENSE).
