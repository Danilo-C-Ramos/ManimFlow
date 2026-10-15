"""Extracts transition frames and checks that each video starts and ends on its states' images."""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import av
import numpy as np
from PIL import Image

from manimflow.plan import Plan, Transition, load_plan
from manimflow.render import QUALITIES

FRAMES_DIR = "quadros"
# Saved as <transition>_<position>.png, e.g. S0-S1_inicio.png.
POSITIONS = ("inicio", "meio", "fim")

# The thresholds that held in the source project: differences under them are
# video compression, not a slide that jumps.
CHANNEL_DIFF = 60
MAX_FRACTION = 0.001
# What Manim encodes MP4 frames in.
VIDEO_PIXEL_FORMAT = "yuv420p"


@dataclass(frozen=True)
class Comparison:
    fraction: float
    matches: bool


def compare_images(
    first: Image.Image,
    second: Image.Image,
    channel_diff: int = CHANNEL_DIFF,
    max_fraction: float = MAX_FRACTION,
) -> Comparison:
    """Two images match when under `max_fraction` of their pixels differ by more than
    `channel_diff` in any channel. Alpha is ignored; images of different sizes never match."""
    if first.size != second.size:
        return Comparison(fraction=1.0, matches=False)
    a = np.asarray(first.convert("RGB"), dtype=np.int16)
    b = np.asarray(second.convert("RGB"), dtype=np.int16)
    differing = (np.abs(a - b) > channel_diff).any(axis=2)
    fraction = float(differing.mean())
    return Comparison(fraction=fraction, matches=fraction < max_fraction)


@dataclass
class FramesReport:
    lesson: Path
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "frames",
            "lesson": str(self.lesson),
            "files": [str(path) for path in self.files],
            "errors": self.errors,
        }


def extract_frames(lesson: Path, transitions: list[str], final: bool) -> FramesReport:
    """Saves the first, middle and last frame of the named transitions (all when none are
    named) and the static image of the states they join (all states when none are named)."""
    report = FramesReport(lesson=lesson.absolute())
    _extract_into(report, transitions, final)
    return report


def _extract_into(report: FramesReport, names: list[str], final: bool) -> list[Transition]:
    """Fills the report and returns the transitions it covers."""
    plan, report.errors = load_plan(report.lesson)
    if plan is None:
        return []
    selected = _select(plan, names, report.errors)
    if report.errors:
        return []
    if names:
        state_ids = list(dict.fromkeys(end for t in selected for end in (t.source, t.target)))
    else:
        state_ids = [state.id for state in plan.states]

    mode = _mode(final)
    rendered = report.lesson / QUALITIES[mode][1]
    frames = _frames_dir(report.lesson, final)
    frames.mkdir(parents=True, exist_ok=True)

    for state_id in state_ids:
        scene = plan.state(state_id).scene
        image = rendered / "png" / f"{scene}.png"
        if not image.is_file():
            report.errors.append(
                f"No {mode} image for state {state_id}: run manimflow {mode} on scene {scene}"
            )
            continue
        target = _state_frame(frames, state_id)
        shutil.copyfile(image, target)
        report.files.append(target)

    for transition in selected:
        video = rendered / "mp4" / f"{transition.scene}.mp4"
        if not video.is_file():
            report.errors.append(
                f"No {mode} video for transition {transition.name}: "
                f"run manimflow {mode} on scene {transition.scene}"
            )
            continue
        for position, frame in zip(POSITIONS, _first_middle_last(video)):
            target = _transition_frame(frames, transition, position)
            frame.save(target)
            report.files.append(target)
    return selected


def _mode(final: bool) -> str:
    """The command whose output is read: "render" for --final, else "preview"."""
    return "render" if final else "preview"


def _frames_dir(lesson: Path, final: bool) -> Path:
    return lesson / QUALITIES[_mode(final)][1] / FRAMES_DIR


def _state_frame(frames: Path, state_id: str) -> Path:
    return frames / f"{state_id}.png"


def _transition_frame(frames: Path, transition: Transition, position: str) -> Path:
    return frames / f"{transition.name}_{position}.png"


def _select(plan: Plan, names: list[str], errors: list[str]) -> list[Transition]:
    by_name = {transition.name: transition for transition in plan.transitions}
    for name in names:
        if name not in by_name:
            known = ", ".join(by_name) or "none"
            errors.append(f"No transition {name} in the plan (transitions: {known})")
    if names:
        return [by_name[name] for name in dict.fromkeys(names) if name in by_name]
    return plan.transitions


def _first_middle_last(video: Path) -> list[Image.Image]:
    """Counts the frames from the packets, without decoding or trusting the header's count,
    then decodes only up to the last one, so a long final-quality video isn't held in memory."""
    with av.open(str(video)) as container:
        count = sum(1 for packet in container.demux(video=0) if packet.size)
    wanted = [0, count // 2, count - 1]
    picked: dict[int, Image.Image] = {}
    with av.open(str(video)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if index in wanted:
                picked[index] = frame.to_image()
    return [picked[index] for index in wanted]


@dataclass(frozen=True)
class Pair:
    """A transition's first or last frame against the static image of the state at that end."""

    transition: str
    position: str
    state: str
    state_image: Path
    frame: Path
    fraction: float
    ok: bool

    def to_dict(self) -> dict:
        return {
            "transition": self.transition,
            "position": self.position,
            "state": self.state,
            "state_image": str(self.state_image),
            "frame": str(self.frame),
            "fraction": self.fraction,
            "ok": self.ok,
        }


@dataclass
class ContinuityReport:
    lesson: Path
    channel_diff: int
    max_fraction: float
    pairs: list[Pair] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "check-continuity",
            "lesson": str(self.lesson),
            "channel_diff": self.channel_diff,
            "max_fraction": self.max_fraction,
            "pairs": [pair.to_dict() for pair in self.pairs],
            "files": [str(path) for path in self.files],
            "errors": self.errors,
        }


def check_continuity(
    lesson: Path,
    transitions: list[str],
    final: bool,
    channel_diff: int = CHANNEL_DIFF,
    max_fraction: float = MAX_FRACTION,
) -> ContinuityReport:
    """Extracts the frames of the named transitions (all when none are named) and checks
    that each starts on its incoming state's image and ends on the next state's image."""
    extracted = FramesReport(lesson=lesson.absolute())
    selected = _extract_into(extracted, transitions, final)
    report = ContinuityReport(
        lesson=extracted.lesson,
        channel_diff=channel_diff,
        max_fraction=max_fraction,
        files=extracted.files,
        errors=extracted.errors,
    )
    frames = _frames_dir(report.lesson, final)
    saved = set(extracted.files)
    for transition in selected:
        for position, state in ((POSITIONS[0], transition.source), (POSITIONS[-1], transition.target)):
            state_image = _state_frame(frames, state)
            frame = _transition_frame(frames, transition, position)
            if state_image not in saved or frame not in saved:
                continue  # already reported as missing
            with Image.open(state_image) as expected, Image.open(frame) as actual:
                comparison = compare_images(_as_in_video(expected), actual, channel_diff, max_fraction)
            pair = Pair(
                transition.name, position, state, state_image, frame, comparison.fraction, comparison.matches
            )
            report.pairs.append(pair)
            if not pair.ok:
                report.errors.append(_mismatch(pair))
    return report


def _as_in_video(image: Image.Image) -> Image.Image:
    """The image with its color at half resolution, as Manim's yuv420p videos store it.

    Thin colored lines and text lose a little saturation in any such video, enough at
    preview size to fail the threshold, and no change to a scene can avoid it. So the
    state image is compared as the video would show it.
    """
    frame = av.VideoFrame.from_image(image.convert("RGB"))
    return frame.reformat(format=VIDEO_PIXEL_FORMAT).to_image()


def _mismatch(pair: Pair) -> str:
    end = "starts on" if pair.position == POSITIONS[0] else "ends on"
    return (
        f"Transition {pair.transition} {end} a different image than state {pair.state}: "
        f"{pair.fraction:.3%} of pixels differ (compare {pair.frame.name} with {pair.state_image.name})"
    )
