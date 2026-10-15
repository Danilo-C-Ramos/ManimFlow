"""Renders one scene inside its own process, so lesson code can't crash the CLI.

Usage: python -m manimflow._worker <scenes_file> <scene> <quality> <media_dir> <out_dir> [settings]

Writes <out_dir>/<scene>.png (the scene's final frame) and, when the scene
plays any animation, its video: <out_dir>/<scene>.mp4, or <out_dir>/<scene>.mov
when the settings ask for a lossless one.

`settings` is a JSON object that overrides what the quality and the lesson's own
code set: "pixel_width" and "pixel_height" (both or neither), "frame_rate",
"background_color" and "lossless".
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def main(
    scenes_file: str, scene_name: str, quality: str, media_dir: str, out_dir: str, settings: str = "{}"
) -> None:
    from manim import Scene, config, tempconfig
    from manim.renderer.cairo_renderer import CairoRenderer
    from PIL import Image

    scenes_path = Path(scenes_file).resolve()
    out = Path(out_dir)
    # Lesson code imports its sibling modules (e.g. fisica.py), as with `manim render`.
    sys.path.insert(0, str(scenes_path.parent))

    with tempconfig({"quality": quality, "media_dir": media_dir}):
        spec = importlib.util.spec_from_file_location(scenes_path.stem, scenes_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # After the lesson's module, which may set config itself (the example sets its background).
        _apply(json.loads(settings), config)

        scene_class = getattr(module, scene_name, None)
        if not (isinstance(scene_class, type) and issubclass(scene_class, Scene)):
            sys.exit(f"Scene {scene_name!r} not found in {scenes_path.name}")

        scene = scene_class()
        scene.render()

        renderer = scene.renderer
        if isinstance(renderer, CairoRenderer):
            # The last play leaves its still mobjects drawn on a background image; drawing
            # every mobject over that again darkens their anti-aliased edges, and the image
            # would no longer match the video's last frame.
            renderer.static_image = None
        renderer.update_frame(scene)
        Image.fromarray(renderer.get_frame()).save(out / f"{scene_name}.png")
        if renderer.num_plays:
            movie = Path(renderer.file_writer.movie_file_path)
            shutil.copyfile(movie, out / f"{scene_name}{movie.suffix}")


def _apply(settings: dict, config) -> None:
    if "pixel_width" in settings:
        width, height = settings["pixel_width"], settings["pixel_height"]
        # A new aspect ratio widens or heightens the lesson's frame, so nothing drawn
        # for it is cut off.
        if width / height >= config.frame_width / config.frame_height:
            config.frame_width = config.frame_height * width / height
        else:
            config.frame_height = config.frame_width * height / width
        config.pixel_width, config.pixel_height = width, height
    if "frame_rate" in settings:
        config.frame_rate = settings["frame_rate"]
    if "background_color" in settings:
        config.background_color = settings["background_color"]
    if settings.get("lossless"):
        # Run-length coded RGB: exact frames, small for flat drawings.
        config.format = "mov"
        config.video_codec = "qtrle"
        config.pixel_format = "rgb24"


if __name__ == "__main__":
    main(*sys.argv[1:])
