# Doctor

`manimflow doctor` checks what rendering and the agent need and says in Portuguese what is missing. `manimflow doctor --install` first installs LaTeX for ManimFlow alone, into ManimFlow's data folder, without admin rights.

```
manimflow doctor [--install] [--json]
```

## Checks

Each check is `ok` or `falta`, with a sentence for the teacher.

| Name | What it looks for |
|---|---|
| `latex` | The `latex` program |
| `dvisvgm` | The `dvisvgm` program, which turns LaTeX output into the shapes Manim draws |
| `latex-packages` | Manim's documented LaTeX packages, found with `kpsewhich` |
| `manim`, `pycairo`, `manimpango`, `pyav` | The Python render stack imports |
| `sandbox` | Linux only: bubblewrap, which Codex runs every agent command in, can start |

The checks look where renders look: ManimFlow's TinyTeX first, then the PATH. A system LaTeX such as MiKTeX passes when it has every package. The package list is the one in Manim's installation docs, minus `ms`, which TeX Live retired.

On Ubuntu 23.10 and later, bubblewrap needs an AppArmor profile. Ubuntu 26.04 ships one, so `sandbox` passes there. On earlier releases, such as 24.04, `sandbox` fails until bubblewrap has ManimFlow's profile, and its message gives the one-line command that installs both, as administrator. Where both profiles are installed, ManimFlow's breaks Ubuntu's, and the message gives the command that removes ManimFlow's. `--install` doesn't run it, because it needs `sudo`. The chat shows the same message instead of starting a turn. See `docs/adr/0002-linux-sandbox-on-ubuntu-uses-an-apparmor-profile.md`.

The command exits non-zero when any check fails or the install fails.

## Install

`--install` downloads TinyTeX-1 from TinyTeX's daily release, unpacks it into ManimFlow's data folder, and then installs the packages from the list that TinyTeX lacks. It skips each part that is already there, so a second run changes nothing and reports `installed: []`. After the install it runs the checks.

The data folder is:

- Windows: `%LOCALAPPDATA%\ManimFlow`. TeX Live breaks on paths with spaces or non-ASCII letters, so a user folder like `C:\Users\José da Silva` makes it fall back to `%ProgramData%\ManimFlow`, as TinyTeX's own installer does. That folder is shared by every user of the computer.
- Elsewhere: `$XDG_DATA_HOME/manimflow`, or `~/.local/share/manimflow`.

TinyTeX goes in its `TinyTeX` folder. The install never runs `tlmgr path add` and never edits the system or user PATH. ManimFlow puts TinyTeX's `bin` folder first on the PATH of its render subprocesses only. Other programs, including an Anaconda install and its Jupyter, see the same PATH as before.

A download that stops halfway leaves nothing in the `TinyTeX` folder: the bundle unpacks into a staging folder next to it and moves in once complete. If the package step fails, running `--install` again picks up the missing packages.

## Report

The JSON report of a check that finds a package missing has this shape:

```json
{
  "ok": false,
  "command": "doctor",
  "install": false,
  "tinytex": "C:\\Users\\prof\\AppData\\Local\\ManimFlow\\TinyTeX",
  "checks": [
    {
      "name": "latex",
      "ok": true,
      "message": "LaTeX encontrado em C:\\Users\\prof\\AppData\\Local\\ManimFlow\\TinyTeX\\bin\\windows\\latex.exe.",
      "path": "C:\\Users\\prof\\AppData\\Local\\ManimFlow\\TinyTeX\\bin\\windows\\latex.exe",
      "missing": []
    },
    {
      "name": "latex-packages",
      "ok": false,
      "message": "Faltam pacotes LaTeX que o Manim usa: physics. Rode `manimflow doctor --install` ...",
      "path": null,
      "missing": ["physics"]
    }
  ],
  "installed": [],
  "duration_s": 1.4,
  "errors": [],
  "install_output": ""
}
```

`installed` lists what this run installed. `errors` holds why an install stopped, in Portuguese, and `install_output` holds what the failing program printed. Without `--json`, install progress goes to stderr and the checks go to stdout, one per line.
