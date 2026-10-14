"""Exports a whole lesson as slide-ready files, following one of the presets in docs/export.md."""

import io
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

from manimflow.plan import Plan, State, Transition, load_plan
from manimflow.render import OUTPUT_DIR, QUALITIES, cache_dir, run_worker

FINAL_QUALITY = QUALITIES["render"][0]
# GIF frame delays are whole hundredths of a second, and browsers slow down anything
# under two hundredths to a tenth of a second.
GIF_MAX_FPS = 50
# What an export writes, and so what the next export of the preset replaces.
EXPORTED_SUFFIXES = {".png", ".mp4", ".gif"}


@dataclass(frozen=True)
class Settings:
    """What every output of an export is rendered at."""

    resolution: int
    fps: int
    aspect_ratio: tuple[int, int]
    # "#rrggbb", or None for the lesson's own background.
    background: str | None = None

    @property
    def size(self) -> tuple[int, int]:
        """Width and height in pixels; the width is rounded to an even number, as video needs."""
        across, down = self.aspect_ratio
        return 2 * round(self.resolution * across / down / 2), self.resolution

    def for_worker(self, lossless: bool) -> dict:
        width, height = self.size
        settings: dict = {"pixel_width": width, "pixel_height": height, "frame_rate": self.fps, "lossless": lossless}
        if self.background:
            settings["background_color"] = self.background
        return settings

    def to_dict(self) -> dict:
        width, height = self.size
        return {
            "resolution": self.resolution,
            "fps": self.fps,
            "aspect_ratio": "{}:{}".format(*self.aspect_ratio),
            "background": self.background,
            "width": width,
            "height": height,
        }


@dataclass
class ExportReport:
    lesson: Path
    preset: str
    settings: Settings
    files: list[Path] = field(default_factory=list)
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    manim_output: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "export",
            "lesson": str(self.lesson),
            "preset": self.preset,
            "settings": self.settings.to_dict(),
            "files": [str(path) for path in self.files],
            "duration_s": round(self.duration_s, 3),
            "errors": self.errors,
            "manim_output": self.manim_output,
        }


def export_lesson(
    lesson: Path,
    preset: str,
    resolution: int | None = None,
    fps: int | None = None,
    aspect_ratio: tuple[int, int] | None = None,
    background: str | None = None,
) -> ExportReport:
    """Renders the lesson at final quality and writes the preset's files, in plan order, to
    the preset's folder in the lesson's output folder. Settings left as None keep the preset's;
    `background` is a "#rrggbb" color."""
    started = time.perf_counter()
    chosen = PRESETS[preset]
    settings = Settings(
        resolution=resolution or chosen.resolution,
        fps=fps or chosen.fps,
        aspect_ratio=aspect_ratio or chosen.aspect_ratio,
        background=background,
    )
    report = ExportReport(lesson=lesson.absolute(), preset=preset, settings=settings)
    if chosen.max_fps and settings.fps > chosen.max_fps:
        report.errors.append(f"The {preset} preset plays at most {chosen.max_fps} fps, not {settings.fps}")
    else:
        _export_into(report)
    report.duration_s = time.perf_counter() - started
    return report


def _export_into(report: ExportReport) -> None:
    plan, report.errors = load_plan(report.lesson)
    if plan is None:
        return
    preset = PRESETS[report.preset]
    slides = _slides(plan, preset.states, preset.transitions)
    folder = report.lesson / OUTPUT_DIR / report.preset
    with tempfile.TemporaryDirectory(dir=cache_dir(report.lesson)) as staging:
        renders = Path(staging) / "cenas"
        exported = Path(staging) / "exportacao"
        renders.mkdir()
        exported.mkdir()
        needed = [slide for slide in slides if not (preset.gif and _reached_by_previous(slide, slides))]
        # GIFs are made from exact frames; Manim only writes those for scenes that animate.
        lossless = {slide.scene for slide in needed if preset.gif and isinstance(slide, Transition)}
        for scene in dict.fromkeys(slide.scene for slide in needed):
            settings = report.settings.for_worker(lossless=scene in lossless)
            worker = run_worker(report.lesson, scene, FINAL_QUALITY, renders, settings)
            if not worker.ok:
                report.manim_output += worker.output
                report.errors.append(worker.error)
        if report.errors:
            return

        preset.write(slides, renders, exported, report)
        if report.errors:
            return

        folder.mkdir(parents=True, exist_ok=True)
        # The previous export may have had more states, or another lesson name; the
        # teacher's own files in the folder stay.
        for old in folder.iterdir():
            if old.is_file() and old.suffix.lower() in EXPORTED_SUFFIXES:
                old.unlink()
        for produced in sorted(exported.iterdir()):
            target = folder / produced.name
            shutil.move(produced, target)
            report.files.append(target)


Slide = State | Transition


def _slides(plan: Plan, states: bool, transitions: bool) -> list[Slide]:
    """The states and transitions asked for, in the order the slides show them: each state
    after the transition that leads to it."""
    incoming = {transition.target: transition for transition in plan.transitions}
    slides: list[Slide] = []
    for state in plan.states:
        if transitions and state.id in incoming:
            slides.append(incoming[state.id])
        if states:
            slides.append(state)
    return slides


def _reached_by_previous(slide: Slide, slides: list[Slide]) -> bool:
    """Whether `slide` is a state that comes right after the transition leading to it."""
    index = slides.index(slide)
    previous = slides[index - 1] if index else None
    return isinstance(slide, State) and isinstance(previous, Transition) and previous.target == slide.id


def _numbered(slides: list[Slide]) -> list[str]:
    """`01_S0`, `02_S0-S1`, ...: names that sort in plan order."""
    digits = max(2, len(str(len(slides))))
    return [
        f"{number:0{digits}}_{slide.id if isinstance(slide, State) else slide.name}"
        for number, slide in enumerate(slides, start=1)
    ]


def _write_files(slides: list[Slide], renders: Path, exported: Path, report: ExportReport) -> None:
    """A numbered PNG per state and MP4 per transition."""
    for slide, name in zip(slides, _numbered(slides)):
        if isinstance(slide, State):
            shutil.copyfile(renders / f"{slide.scene}.png", exported / f"{name}.png")
        elif video := _transition_video(slide, renders, ".mp4", report):
            shutil.copyfile(video, exported / f"{name}.mp4")


def _write_video(slides: list[Slide], renders: Path, exported: Path, report: ExportReport) -> None:
    """One video of the transitions, named after the lesson."""
    if not slides:
        report.errors.append("The plan has no transitions to put in a video")
        return
    videos = [_transition_video(slide, renders, ".mp4", report) for slide in slides if isinstance(slide, Transition)]
    if report.errors:
        return
    _concatenate([video for video in videos if video], exported / f"{report.lesson.name}.mp4")


def _write_gifs(slides: list[Slide], renders: Path, exported: Path, report: ExportReport) -> None:
    """A numbered GIF per transition and a single-frame GIF per state, all with one palette.

    A state reached by a transition is that GIF's last frame, so the slide doesn't change
    when the GIF ends; any other state is its scene's image.
    """
    sources: list[Path | None] = []
    for slide in slides:
        if isinstance(slide, Transition):
            sources.append(_transition_video(slide, renders, ".mov", report))
        else:
            sources.append(None if _reached_by_previous(slide, slides) else renders / f"{slide.scene}.png")
    if report.errors:
        return
    found = [source for source in sources if source]
    palette = _palette(found, report.settings.size)
    last_frame = None
    for slide, source, name in zip(slides, sources, _numbered(slides)):
        frames = _frames(source) if source else [last_frame]
        last_frame = _write_gif(frames, palette, report.settings.fps, exported / f"{name}.gif")


@dataclass(frozen=True)
class _Palette:
    image: Image.Image  # for Pillow to map colors onto
    argb: np.ndarray  # for the GIF encoder


def _frames(source: Path):
    """The RGB frames of a video, or the single image of a PNG, one at a time."""
    if source.suffix == ".png":
        with Image.open(source) as image:
            yield np.asarray(image.convert("RGB"))
        return
    with av.open(str(source)) as container:
        for frame in container.decode(video=0):
            yield frame.to_ndarray(format="rgb24")


def _palette(sources: list[Path], size: tuple[int, int]) -> _Palette:
    """The 256 colors that best cover every frame of every source, chosen by ffmpeg's palettegen."""
    graph = av.filter.Graph()
    width, height = size
    buffer = graph.add_buffer(width=width, height=height, format="rgb24", time_base=Fraction(1, 100))
    palettegen = graph.add("palettegen", "max_colors=256:reserve_transparent=0:stats_mode=full")
    sink = graph.add("buffersink")
    buffer.link_to(palettegen)
    palettegen.link_to(sink)
    graph.configure()
    count = 0
    for source in sources:
        for pixels in _frames(source):
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = count
            count += 1
            graph.push(frame)
    graph.push(None)
    bgra = graph.pull().to_ndarray().reshape(256, 4)
    rgb = np.ascontiguousarray(bgra[:, [2, 1, 0]])
    image = Image.new("P", (1, 1))
    image.putpalette(rgb.tobytes())
    argb = np.ascontiguousarray(np.concatenate([np.full((256, 1), 255, np.uint8), rgb], axis=1))
    return _Palette(image, argb)


def _write_gif(frames, palette: _Palette, fps: int, target: Path) -> np.ndarray:
    """Writes the frames, mapped onto the palette without dithering, as a GIF that plays
    once; returns the last frame."""
    last = None
    with av.open(str(target), mode="w", format="gif", options={"loop": "-1"}) as output:
        stream = output.add_stream("gif", rate=fps)
        stream.pix_fmt = "pal8"
        stream.codec_context.time_base = Fraction(1, 100)
        for index, pixels in enumerate(frames):
            last = pixels
            indices = np.asarray(
                Image.fromarray(pixels).quantize(palette=palette.image, dither=Image.Dither.NONE)
            )
            if index == 0:
                stream.height, stream.width = indices.shape
            # PyAV takes pal8 frames as an (indices, palette) pair; its stubs only list arrays.
            frame = av.VideoFrame.from_ndarray((indices, palette.argb), format="pal8")  # type: ignore[arg-type]
            frame.time_base = Fraction(1, 100)
            frame.pts = round(index * 100 / fps)
            output.mux(stream.encode(frame))
        output.mux(stream.encode())
    assert last is not None
    return last


def _transition_video(slide: Transition, renders: Path, suffix: str, report: ExportReport) -> Path | None:
    video = renders / f"{slide.scene}{suffix}"
    if video.is_file():
        return video
    report.errors.append(f"Transition {slide.name} has no video: scene {slide.scene} plays no animation")
    return None


def _concatenate(videos: list[Path], target: Path) -> None:
    """Joins videos encoded alike without re-encoding them, as Manim joins a scene's animations."""
    manifest = "".join(f"file 'file:{_quoted(video.as_posix())}'\n" for video in videos)
    with (
        av.open(io.BytesIO(manifest.encode("utf-8")), mode="r", format="concat", options={"safe": "0"}) as source,
        av.open(str(target), mode="w") as output,
    ):
        stream = source.streams.video[0]
        joined = output.add_stream_from_template(template=stream)
        for packet in source.demux(stream):
            # Flushing packets carry no data, and each file's timestamps start over.
            if packet.dts is None:
                continue
            packet.dts = None
            packet.stream = joined
            output.mux(packet)


def _quoted(path: str) -> str:
    """The path inside single quotes of an ffmpeg concat manifest."""
    return path.replace("'", "'\\''")


@dataclass(frozen=True)
class Preset:
    name: str
    help: str
    resolution: int
    fps: int
    # Which slides the preset exports, and how it writes them.
    states: bool
    transitions: bool
    write: Callable[[list[Slide], Path, Path, ExportReport], None]
    aspect_ratio: tuple[int, int] = (16, 9)
    # GIF presets render transitions losslessly and take a state reached by a
    # transition from its last frame.
    gif: bool = False
    max_fps: int | None = None


PRESETS = {
    preset.name: preset
    for preset in [
        Preset(
            "powerpoint",
            "PowerPoint: a PNG per state and an MP4 per transition",
            resolution=1080,
            fps=60,
            states=True,
            transitions=True,
            write=_write_files,
        ),
        Preset(
            "web",
            "PowerPoint web / Google Slides: a GIF per transition and a static GIF per state",
            resolution=720,
            fps=25,
            states=True,
            transitions=True,
            write=_write_gifs,
            gif=True,
            max_fps=GIF_MAX_FPS,
        ),
        Preset(
            "beamer",
            "Beamer / PDF: a PNG per state",
            resolution=1080,
            fps=60,
            states=True,
            transitions=False,
            write=_write_files,
        ),
        Preset(
            "video",
            "the whole lesson: every transition in one MP4",
            resolution=1080,
            fps=60,
            states=False,
            transitions=True,
            write=_write_video,
        ),
    ]
}
