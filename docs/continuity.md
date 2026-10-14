# Frames and the continuity check

A transition is a video that starts on one state's image and ends on the next one's. If the first or last frame differs from the image on the slide, the slide jumps when the video starts or ends. `manimflow frames` saves the frames to look at, and `manimflow check-continuity` measures the difference.

Neither command renders anything. They read what `manimflow preview` wrote (`saida/previa/`), or with `--final` what `manimflow render` wrote (`saida/`). A missing image or video is an error that names the scene to render.

## Naming transitions

Both commands name a transition after the states it joins, so `S0-S1` goes from `S0` to `S1`. State ids are plain identifiers, so the hyphen is unambiguous. The commands take any number of names after the lesson folder, and use every transition in `plano.yaml` when given none.

```
manimflow frames <lesson> [S0-S1 ...] [--final] [--json]
manimflow check-continuity <lesson> [S0-S1 ...] [--final] [--channel-diff 60] [--max-fraction 0.001] [--json]
```

## Frame files

Frames go to `quadros/` next to the `png/` and `mp4/` folders they come from (`saida/previa/quadros/` or `saida/quadros/`):

| File | What it is |
|---|---|
| `S0.png` | The static image of state `S0`: the last frame of its scene, as the slide shows it. |
| `S0-S1_inicio.png` | The first frame of the `S0-S1` video. |
| `S0-S1_meio.png` | The middle frame. |
| `S0-S1_fim.png` | The last frame. |

With no transitions named, `frames` saves every state's image. With some named, it saves the images of the states those transitions join. `check-continuity` saves the same files as `frames` before comparing them.

## The check

For each transition, the check compares two pairs.

- `inicio`: the incoming state's image against the video's first frame;
- `fim`: the next state's image against the video's last frame.

A pixel differs when any of its color channels differs by more than `--channel-diff` (default 60). Two images match when the fraction of differing pixels is below `--max-fraction` (default 0.001, that is 0.1%). These thresholds held in the source project; differences under them are video compression. Images of different sizes never match. The check ignores alpha.

Before comparing, the check converts the state image to yuv420p, the pixel format of Manim's videos, which stores color at half resolution. Every such video loses a little saturation on thin colored lines and text, and at preview size that alone failed most pairs of the bundled example. No change to a scene can avoid it, so the check compares the state image as the video would show it. A moved, added or missing object still fails. The saved `S0.png` is the original image.

## Report

The command exits non-zero when any pair fails or anything is missing. Each failing pair also gets a message in `errors` that names the transition, the end and both files. The JSON report has this shape:

```json
{
  "ok": false,
  "command": "check-continuity",
  "lesson": "/path/to/Aula 09",
  "channel_diff": 60,
  "max_fraction": 0.001,
  "pairs": [
    {
      "transition": "S0-S1",
      "position": "fim",
      "state": "S1",
      "state_image": "/path/to/Aula 09/saida/previa/quadros/S1.png",
      "frame": "/path/to/Aula 09/saida/previa/quadros/S0-S1_fim.png",
      "fraction": 0.0123,
      "ok": false
    }
  ],
  "files": ["/path/to/Aula 09/saida/previa/quadros/S0.png", "..."],
  "errors": ["Transition S0-S1 ends on a different image than state S1: 1.230% of pixels differ (compare S0-S1_fim.png with S1.png)"]
}
```

`frames --json` reports `ok`, `command`, `lesson`, `files` and `errors` in the same way.
