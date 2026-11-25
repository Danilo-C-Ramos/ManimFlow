# ManimFlow

ManimFlow is a local app for teachers who want [Manim](https://www.manim.community/) animations for their slides without learning Manim. You describe the animation in Portuguese in a chat. An agent (OpenAI's Codex, signed in with your ChatGPT plan or an API key) writes the physics and the drawing as separate files. It renders previews, looks at the frames and fixes what it sees before it answers. Each lesson is a plain folder on your computer.

The interface is in Brazilian Portuguese. The code and these docs are in English.

ManimFlow is in early development and isn't on PyPI yet, so it runs from a copy of this repository.

## Install on Windows

Windows is the supported platform for v0.1. You need no administrator rights, and an existing Anaconda or Jupyter install stays as it is.

1. Install [uv](https://docs.astral.sh/uv/). In PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Close and reopen PowerShell so it finds `uv`.

2. Get ManimFlow. On the repository's GitHub page, click **Code**, then **Download ZIP**, and unzip it with **Extrair tudo**. If you have git, `git clone https://github.com/Danilo-C-Ramos/ManimFlow.git` does the same. Any folder works, including one with spaces or accents in its name.

3. Open PowerShell in the ManimFlow folder, the one with `README.md` and `pyproject.toml` in it. In File Explorer, open that folder, type `powershell` in the address bar and press Enter.

4. Install LaTeX for ManimFlow. Manim needs it to write equations.

   ```powershell
   uv run manimflow doctor --install
   ```

   The first time, `uv run` downloads Python 3.12 and ManimFlow's libraries into a `.venv` folder inside the ManimFlow folder. Then `doctor --install` downloads TinyTeX and the LaTeX packages Manim uses into `%LOCALAPPDATA%\ManimFlow\TinyTeX`. LaTeX breaks on folders with spaces or accents, so if your user name has one (`C:\Users\José da Silva`), TinyTeX goes into `%ProgramData%\ManimFlow\TinyTeX` instead, shared by every user of the computer. It all takes a few minutes the first time. It then checks everything rendering needs and says in Portuguese what is still missing. Nothing changes in your PATH, so other programs don't see this LaTeX. Run `uv run manimflow doctor` later to check again.

5. Start ManimFlow:

   ```powershell
   uv run manimflow
   ```

To start it again another day, open PowerShell in the ManimFlow folder and run `uv run manimflow`.

## First run

`uv run manimflow` starts a local server on `127.0.0.1` and opens it in your browser. Nothing is reachable from other computers. Keep the PowerShell window open while you work; closing it stops ManimFlow.

1. The home page asks "O que vamos animar hoje?". Describe an animation there to start a lesson, or click **Abrir o exemplo** to open the bundled example, special relativity with a hero and a mirror.
2. Sign in. The first lesson you open asks for it. "Entrar com o ChatGPT" opens ChatGPT's login page and uses your ChatGPT plan. Plus, Pro and the business plans run on GPT-6.2-Sol. Free and Go accounts get GPT-6 Luna, with smaller usage limits; OpenAI says Free access is still rolling out. You can also paste an OpenAI API key instead. `uv run manimflow account` shows your plan and the models it includes ([docs/models.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/models.md)). ManimFlow keeps these credentials in its own folder, apart from any Codex you installed yourself.
3. The first time the agent runs, Windows may ask for administrator permission. That sets up the sandbox that keeps the agent inside the lesson folder and off the internet. You can decline. The agent then still writes only inside the lesson, but it can reach the internet.

Your lessons go into `Documentos\Aulas Manim`; **Mudar pasta** on the home page picks another folder. Turmas group them, one folder per turma. The example lives in `%LOCALAPPDATA%\ManimFlow\exemplo`, and your changes to it stay there.

To try the app without signing in, run `uv run manimflow --demo`. A scripted agent answers instead of Codex.

## Manual install steps

**Your own LaTeX.** If you already use MiKTeX or TeX Live, you can skip `doctor --install`. Run `uv run manimflow doctor`: it lists the LaTeX packages Manim needs that your distribution lacks. Install those with your distribution's package manager, such as MiKTeX Console, until `doctor` passes. See [docs/doctor.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/doctor.md) for the checks and the package list.

**Updating.** Download the new ZIP and unzip it over the old folder, or run `git pull` in a clone. The next `uv run manimflow` installs whatever changed.

**Uninstall.** Delete the ManimFlow folder, and run `uv cache clean` to remove what uv downloaded. Then delete `%LOCALAPPDATA%\ManimFlow`, which holds the sign-in, the example lesson copy and usually TinyTeX, and `%ProgramData%\ManimFlow` if TinyTeX went there. Your own lesson folders stay where they are.

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

On Linux, `uv sync` builds `pycairo` and `manimpango` from source, so install the cairo and pango headers first (`libcairo2-dev libpango1.0-dev pkg-config` on Debian and Ubuntu). On Ubuntu 24.04, the agent's sandbox needs an AppArmor profile, and `uv run manimflow doctor` prints the command that installs it. Ubuntu 26.04 ships a profile of its own.

`uv run pytest` skips the smoke test, which drives the real Codex agent and spends quota. Run it with `uv run pytest -m smoke` after signing in.

CI also unzips the repository on a clean Windows runner, follows the install steps above, and goes through the app in Edge with `.github/try_the_app.py`. The screenshots are in each run's `telas-windows` artifact.

The design is in [docs/design.md](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/docs/design.md), and the decisions behind it are in [docs/adr/](https://github.com/Danilo-C-Ramos/ManimFlow/tree/main/docs/adr).

### Releasing

The version comes from the git tag. Pushing a tag such as `v0.0.2` runs the release workflow. It runs the tests, builds the package, runs `uvx manimflow --help`, `doctor --install` and `doctor` from the built wheel on a clean Windows runner, and publishes to PyPI with trusted publishing. Once it is on PyPI, `uvx manimflow` runs ManimFlow without a copy of the repository. No token is stored in the repository.

```bash
git tag v0.0.2
git push origin v0.0.2
```

## License

MIT. See [LICENSE](https://github.com/Danilo-C-Ramos/ManimFlow/blob/main/LICENSE).
