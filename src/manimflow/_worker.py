"""Renders one scene inside its own process, so lesson code can't crash the CLI.

Usage: python -m manimflow._worker <scenes_file> <scene> <quality> <media_dir> <out_dir>

Writes <out_dir>/<scene>.png (the scene's final frame) and, when the scene
plays any animation, <out_dir>/<scene>.mp4.
"""

import importlib.util
import shutil
import sys
from pathlib import Path


def main(scenes_file: str, scene_name: str, quality: str, media_dir: str, out_dir: str) -> None:
    from manim import Scene, tempconfig
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
            shutil.copyfile(renderer.file_writer.movie_file_path, out / f"{scene_name}.mp4")


if __name__ == "__main__":
    main(*sys.argv[1:])
