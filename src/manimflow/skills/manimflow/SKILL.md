---
name: manimflow
description: How to render, inspect and check a ManimFlow lesson with the manimflow CLI, and the self-check loop to run after every change to the lesson.
---

# The manimflow CLI and the self-check loop

Every render goes through the `manimflow` CLI, run from the lesson folder (`.`). Never call `manim` directly. Every subcommand exits non-zero on failure and prints what went wrong. Add `--json` for a machine-readable report with `ok`, the `files` it produced and its `errors`.

## Subcommands

### `manimflow plan validate .`

Checks `plano.yaml`: required fields, unique state ids, transitions between neighbouring states, and scene names that exist as scene classes in `cenas.py`. Run it after every edit to `plano.yaml` or to the class names in `cenas.py`, and before rendering anything else. Its messages are in Portuguese and can be shown to the teacher as they are.

### `manimflow preview . <Scene>`

Renders one scene class of `cenas.py` at low quality into `saida/previa/`: the scene's last frame as `png/<Scene>.png`, and its video as `mp4/<Scene>.mp4` when the scene animates. This is the render you use while you work. Run it for every scene you changed, and for every scene that reads something you changed in `fisica.py`.

### `manimflow frames . [S0-S1 ...]`

Saves frames from the preview into `saida/previa/quadros/`: `S0-S1_inicio.png`, `S0-S1_meio.png` and `S0-S1_fim.png` for each named transition, and `S0.png`, `S1.png` for the states it joins. A transition is named after the states in `plano.yaml` it joins. With no names it takes every transition in the plan. It renders nothing, so run `preview` first. Use it when you only want to look at a transition; `check-continuity` saves the same frames.

### `manimflow check-continuity . [S0-S1 ...]`

Checks that each transition starts exactly on the image of the state it leaves and ends exactly on the image of the state it reaches, so the slide doesn't jump when the video starts or ends. It saves the same frames as `frames` and compares them. On failure, each error names the transition, the end (`inicio` or `fim`) and the two files to compare. Look at both before changing anything: usually an object is in a different place, has a different color or size, or is missing at one end.

### `manimflow render . <Scene>`

Renders at final quality into `saida/png/` and `saida/mp4/`. It is slow. Run it only when the teacher asks for the final version. Export from the app renders final quality on its own.

`frames` and `check-continuity` accept `--final` to read the final render instead of the preview.

## The self-check loop

After every change to the lesson, check your work before you answer the teacher:

1. If you changed `plano.yaml`, run `manimflow plan validate .`.
2. Run the lesson's physics tests: `python -m pytest -q -p no:cacheprovider test_fisica.py`. If you changed `fisica.py`, first update `test_fisica.py` so it checks every value `equacoes()` returns, against values worked out by hand rather than recomputed with the formulas of `fisica.py`. A failing physics test is a problem to fix, like a broken render.
3. Run `manimflow preview . <Scene>` for each scene the change touches.
4. Run `manimflow check-continuity . <transition> ...` for each transition whose scene you rendered, and for each transition that starts or ends on a state whose `cena` you rendered: a change to a scene's last frame changes that state's image, which the next transition must start on. Preview first any other scene those transitions and states use, if `saida/previa/` doesn't have it yet. The check also saves their frames, so you don't need `frames` here.
5. Look at the first, middle and last frame of each of those transitions, and at the images of the states they join, with your image viewing tool, even when the check passes. Check them against the plan and the teacher's request: right objects, positions, colors and text, nothing cut off or overlapping, labels readable, Portuguese text with a decimal comma when the profile asks for it.

An attempt is one pass through these steps. When a step fails or the frames look wrong, fix the cause and run the steps again. That is the next attempt. Make at most 4 attempts per teacher request. If the work is still not right after the 4th, stop and tell the teacher, in Portuguese:

- what works now;
- what is still wrong, naming the transition, state or test;
- what you would try next.

Don't render at final quality inside this loop.
