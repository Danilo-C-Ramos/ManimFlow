# Export presets

`manimflow export` renders the whole lesson at final quality and writes files to drop into slides. Each preset targets one presentation tool. The command always renders the scenes again, because the preset decides the resolution, frame rate, background and aspect ratio, so it never reads what `preview` or `render` wrote.

```
manimflow export <lesson> <preset> [--resolution 1080] [--fps 60] [--aspect-ratio 16:9] [--background white] [--json]
```

## Presets

| Preset | Files | Defaults |
|---|---|---|
| `powerpoint` | A PNG per state and an MP4 per transition | 1080p, 60 fps |
| `web` | PowerPoint web / Google Slides: a GIF per transition and a single-frame GIF per state | 720p, 25 fps |
| `beamer` | Beamer / PDF: a PNG per state | 1080p, 60 fps |
| `video` | The whole lesson: every transition in one MP4 | 1080p, 60 fps |

Every preset defaults to 16:9 and to the lesson's own background.

## Settings

These flags override the preset's defaults for every file it writes.

- `--resolution` is the height in pixels, an even number from 16 to 1440. 4K comes in v0.2. The width follows from the aspect ratio and is rounded to an even number, as video needs.
- `--fps` sets the frames per second, from 1 to 120. The `web` preset stops at 50. GIF frame delays are whole hundredths of a second, and browsers slow anything shorter than two hundredths down to a tenth. Rates that don't divide 100, such as 30, get delays that alternate (30, 40, 30 ms), which can make motion a little uneven. 25 and 50 play evenly.
- `--aspect-ratio` takes `width:height`, from 1:4 to 4:1. A new ratio widens or heightens the lesson's frame, so the drawing is never cropped. At 4:3, a lesson drawn for 16:9 keeps its full width and gets more room above and below.
- `--background` takes a color such as `#ffffff` or `white`. It overrides `config.background_color` in `cenas.py`, but not a scene that sets `self.camera.background_color` in `construct()`.

## Files

Files go to the preset's folder inside the lesson's output folder, `saida/powerpoint/`, `saida/web/`, `saida/beamer/` or `saida/video/`. Their numbers follow the order of the slides, so a file manager lists them in presentation order. Each state comes right after the transition that leads to it.

```
saida/powerpoint/01_S0.png
saida/powerpoint/02_S0-S1.mp4
saida/powerpoint/03_S1.png
```

`beamer` numbers only the states, and `web` names its files the same way as `powerpoint`, with `.gif`. `video` writes one file named after the lesson folder, such as `saida/video/Aula 09 - Minkowski.mp4`. A plain slide change, two states with no transition between them, adds nothing to that video.

An export replaces the PNG, MP4 and GIF files of the preset's previous export, and leaves other files in the folder alone. If any scene fails to render, the command writes nothing and the previous export stays.

## GIFs

The `web` preset renders transitions to lossless video, so its GIFs come from exact frames and not from a compressed MP4. Then it works in two passes:

1. ffmpeg's `palettegen` picks 256 colors from every frame of every transition and every state image that goes into a GIF. That palette is the lesson's palette.
2. Each frame is mapped onto that palette without dithering, so the same image always gives the same pixels.

Every GIF of the lesson has only that palette as its global color table, with no per-frame tables. A transition GIF plays once and stays on its last frame. The GIF of a state reached by a transition is that last frame, saved alone, so nothing shifts when the slide changes. A state with no transition leading to it uses its scene's image.

## Whole-lesson video

The `video` preset joins the transitions in plan order with ffmpeg's concat demuxer, as Manim joins the animations of one scene. All transitions are rendered with the same settings, so their streams join without re-encoding and lose no quality. A lesson with no transitions has no video, which is an error. The video has no sound: the join copies only the picture, so a scene's `add_sound` is lost there. The `powerpoint` MP4s keep it.

## Report

The command exits non-zero when the plan is invalid, a scene fails, or a transition's scene plays no animation. The JSON report has this shape:

```json
{
  "ok": true,
  "command": "export",
  "lesson": "/path/to/Aula 09",
  "preset": "powerpoint",
  "settings": {
    "resolution": 1080,
    "fps": 60,
    "aspect_ratio": "16:9",
    "background": null,
    "width": 1920,
    "height": 1080
  },
  "files": [
    "/path/to/Aula 09/saida/powerpoint/01_S0.png",
    "/path/to/Aula 09/saida/powerpoint/02_S0-S1.mp4",
    "/path/to/Aula 09/saida/powerpoint/03_S1.png"
  ],
  "duration_s": 41.2,
  "errors": [],
  "manim_output": "",
  "failed_scenes": []
}
```

`manim_output` holds the output of every scene that failed, as in the `render` report, and `failed_scenes` names those scenes.

While it runs, the command reports its progress on stderr, one line per scene it is about to render and one when it writes the files. With `--json`, each line is a JSON object, `{"progress": {"scene": "S0", "number": 1, "of": 3}}`, with `"scene": null` for the files. The export dialog reads these lines and shows `Renderizando a cena S0 (1 de 3)…`. When a scene fails, the dialog names it in Portuguese and keeps the English errors and Manim's output under "Detalhes para o agente".
