# ManimFlow on macOS and Linux

macOS and Linux are not officially supported in v0.1. Windows is the platform ManimFlow is built and tested for (see the [README](../README.md)). CI also runs on Linux, and the path below has been tried there, but no release is checked against it.

The problem on these systems is the render stack. `pycairo` has no macOS wheels, and on Linux `pycairo` and `manimpango` build from source against the system's cairo and pango headers. [pixi](https://pixi.sh) avoids that: it installs Manim and its native libraries as prebuilt conda-forge packages into a project folder, with no Homebrew, no system packages and no administrator rights, and then installs ManimFlow from PyPI on top.

## Install

1. Install pixi:

   ```bash
   curl -fsSL https://pixi.sh/install.sh | sh
   ```

   Open a new terminal so it finds `pixi`.

2. Create a folder for ManimFlow, with Python 3.12 and Manim from conda-forge, and ManimFlow from PyPI:

   ```bash
   pixi init manimflow
   cd manimflow
   pixi add "python=3.12.*" manim
   pixi add --pypi manimflow
   ```

   conda-forge's `manim` brings `pycairo`, `manimpango`, `av` and `ffmpeg` already built. pixi sees them when it installs ManimFlow, so nothing compiles.

3. Install LaTeX and check the rest:

   ```bash
   pixi run manimflow doctor --install
   ```

   On Linux x86_64 this puts TinyTeX into `~/.local/share/manimflow`, as on Windows. There is no TinyTeX bundle for macOS or Linux on ARM, so there `--install` stops with a message. Install a TeX distribution yourself instead (MacTeX or BasicTeX on macOS, TeX Live from your distribution on Linux) and add the packages that `pixi run manimflow doctor` reports missing. [doctor.md](doctor.md) lists them.

4. Start ManimFlow from that folder:

   ```bash
   pixi run manimflow
   ```

To update, run `pixi update` in the folder.

## Linux: the agent's sandbox

Codex runs every agent command inside bubblewrap. On Ubuntu 23.10 and later, user namespaces are restricted, and bubblewrap needs an AppArmor profile. Ubuntu 26.04 ships one. On earlier releases, such as 24.04, bubblewrap can't start until it has ManimFlow's. `pixi run manimflow doctor` reports this and prints the one command, run with `sudo`, that installs bubblewrap and the profile. The chat shows the same message instead of starting a turn. See [ADR 0002](adr/0002-linux-sandbox-on-ubuntu-uses-an-apparmor-profile.md).

## Without pixi

On Linux, `uvx manimflow` also works once the cairo and pango headers are installed (`libcairo2-dev libpango1.0-dev pkg-config` on Debian and Ubuntu), because uv then builds `pycairo` and `manimpango` from source. On macOS, Manim's own [installation docs](https://docs.manim.community/en/stable/installation/uv.html) list the Homebrew packages that do the same job.
