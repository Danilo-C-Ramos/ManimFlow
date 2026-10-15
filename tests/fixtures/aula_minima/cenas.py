"""Minimal fixture lesson: one static state and one short transition."""

from manim import BLUE, RIGHT, Scene, Square


class S0(Scene):
    def construct(self):
        self.add(Square(color=BLUE))


class T01(Scene):
    def construct(self):
        quadrado = Square(color=BLUE)
        self.add(quadrado)
        self.play(quadrado.animate.shift(RIGHT), run_time=0.5)
