# The Linux sandbox on Ubuntu uses an AppArmor profile

Codex runs every agent command inside bubblewrap: the `bwrap` on the PATH, or else the one bundled with Codex. Bubblewrap needs an unprivileged user namespace, and its own network namespace for "no network". Ubuntu 23.10 and later set `kernel.apparmor_restrict_unprivileged_userns=1`, which lets a program without an AppArmor profile create the namespace but not configure it. Bubblewrap stops with `loopback: Failed RTM_NEWADDR: Operation not permitted`, and the agent can't run a single command. GitHub's Ubuntu 24.04 runners behave the same way.

Codex 0.162 has no fallback: with `features.use_legacy_landlock` it refuses to run filesystem-restricted commands without bubblewrap.

ManimFlow ships an AppArmor profile, `src/manimflow/apparmor/manimflow-bwrap`, that allows user namespaces for `/usr/bin/bwrap` alone. The fix for the teacher is one command, run once as administrator: install Ubuntu's `bubblewrap` package and load the profile. Codex picks the system `bwrap` over its bundled copy.

## Ubuntu 26.04 ships its own profile

Ubuntu 26.04 loads `/etc/apparmor.d/bwrap-userns-restrict`, Ubuntu's own profile for `/usr/bin/bwrap`, so bubblewrap starts there without ManimFlow's. Adding ManimFlow's profile on top replaces Ubuntu's for `/usr/bin/bwrap`, and bubblewrap fails again with the same `RTM_NEWADDR` error. GitHub's Ubuntu 26.04 runners showed both. So the check suggests the profile only where Ubuntu's is missing. Where both are installed, as after an upgrade from 24.04, it gives the command that removes ManimFlow's.

## Why not turn the restriction off

`sysctl kernel.apparmor_restrict_unprivileged_userns=0` also works. It lifts the restriction for every program on the computer, though. The restriction is a protection that Ubuntu added against kernel exploits, so ManimFlow shouldn't ask teachers to switch it off. The profile only opens it for bubblewrap, which is the reason bubblewrap needs it in the first place.

## Consequences

- `manimflow doctor` has a `sandbox` check on Linux. When it fails, the message has the command. `--install` doesn't run it, because it needs `sudo` and the rest of the install needs no admin rights.
- When the sandbox can't start, the chat answers every message with the same explanation and doesn't call the model, so no quota is spent on turns whose commands would all fail.
- CI on Ubuntu runs that same command before the tests when the check fails, as teachers would. On a 24.04 runner the shipped profile is what makes the sandbox tests pass; on a 26.04 runner Ubuntu's own profile does.
- The restriction comes from an Ubuntu kernel patch, so derivatives such as Linux Mint 22 get the same message and command. Any other failure shows bubblewrap's own error, with no command.
