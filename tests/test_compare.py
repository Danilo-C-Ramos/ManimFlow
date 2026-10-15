import numpy as np
from PIL import Image

from manimflow.continuity import compare_images

# 1000 x 1000 pixels, so 1000 pixels are exactly 0.1%.
SIDE = 1000


def gray(value: int) -> np.ndarray:
    return np.full((SIDE, SIDE, 3), value, dtype=np.uint8)


def with_changed_pixels(base: np.ndarray, count: int, delta: int, channel: int = 0) -> Image.Image:
    changed = base.astype(np.int16)
    changed.reshape(-1, 3)[:count, channel] += delta
    return Image.fromarray(changed.astype(np.uint8))


def test_identical_images_match():
    result = compare_images(Image.fromarray(gray(100)), Image.fromarray(gray(100)))

    assert result.fraction == 0
    assert result.matches


def test_just_under_a_tenth_of_a_percent_of_differing_pixels_matches():
    result = compare_images(Image.fromarray(gray(100)), with_changed_pixels(gray(100), 999, 61))

    assert result.fraction == 0.000999
    assert result.matches


def test_a_tenth_of_a_percent_of_differing_pixels_does_not_match():
    result = compare_images(Image.fromarray(gray(100)), with_changed_pixels(gray(100), 1000, 61))

    assert result.fraction == 0.001
    assert not result.matches


def test_differences_of_60_or_less_are_compression_noise():
    result = compare_images(Image.fromarray(gray(100)), with_changed_pixels(gray(100), 5000, 60))

    assert result.fraction == 0
    assert result.matches


def test_any_single_channel_counts():
    result = compare_images(Image.fromarray(gray(100)), with_changed_pixels(gray(100), 2000, 61, channel=2))

    assert result.fraction == 0.002


def test_difference_in_either_direction_counts():
    result = compare_images(Image.fromarray(gray(200)), with_changed_pixels(gray(200), 2000, -61))

    assert result.fraction == 0.002


def test_thresholds_are_configurable():
    noisy = with_changed_pixels(gray(100), 5000, 30)

    strict = compare_images(Image.fromarray(gray(100)), noisy, channel_diff=20)
    lenient = compare_images(Image.fromarray(gray(100)), noisy, channel_diff=20, max_fraction=0.01)

    assert strict.fraction == 0.005
    assert not strict.matches
    assert lenient.matches


def test_alpha_is_ignored():
    # Manim saves state images as RGBA; decoded video frames are RGB.
    rgba = Image.fromarray(np.dstack([gray(100), np.full((SIDE, SIDE), 255, dtype=np.uint8)]))

    assert compare_images(rgba, Image.fromarray(gray(100))).matches


def test_images_of_different_sizes_do_not_match():
    small = Image.fromarray(np.full((10, 10, 3), 100, dtype=np.uint8))

    result = compare_images(small, Image.fromarray(gray(100)))

    assert result.fraction == 1
    assert not result.matches
