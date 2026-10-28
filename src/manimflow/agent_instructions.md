# Working on a ManimFlow lesson

You work inside one lesson folder of ManimFlow, a tool a physics teacher uses to make Manim animations for slides. The teacher writes in Brazilian Portuguese and does not program.

- Before changing anything, read the teacher's profile (`../perfil.md`) and the lesson's `CONTEXTO.md`, and follow both. When the teacher settles a new rule or decision, record it in `CONTEXTO.md` so the next session knows it.
- Physics goes in `fisica.py` and drawing goes in `cenas.py`. `cenas.py` takes its numbers from `fisica.py` and computes no physics of its own.
- `fisica.py` exposes `equacoes()`: a list of the lesson's equations in presentation order, each with a name, a LaTeX expression, a numeric value and a unit (`""` when there is none). The teacher checks the physics in ManimFlow's equations panel, which shows exactly this list, so keep it in step with every change to the physics.
- Render only through the `manimflow` CLI: `manimflow preview . <Scene>` while you work, and `manimflow render . <Scene>` only when the teacher asks for the final version. Never call `manim` directly. The `manimflow` skill explains each subcommand.
- Check your own work before you answer. After every change to the lesson, run the self-check loop of the `manimflow` skill: preview the changed scenes, run the physics tests, check continuity, and look at the first, middle and last frame of each changed transition. Fix what is wrong and check again.
- Make at most 4 attempts per request. If it still isn't right after the 4th, stop and tell the teacher what works, what is still wrong and what you would try next. Never hand over work you haven't checked as if it were done.
- Keep `test_fisica.py` up to date: it checks every value `equacoes()` in `fisica.py` returns, and you run it with `python -m pytest -q -p no:cacheprovider test_fisica.py` on every change.
- Comment the intent of each movement in `cenas.py` (`# este movimento mostra…`), so the teacher can follow the code.
- Write everything the teacher reads in Brazilian Portuguese: your replies, `CONTEXTO.md`, `plano.yaml`, code comments and the text inside the scenes.
- Never install packages with pip, conda, uv or anything else. If the work seems to need a new library, stop and tell the teacher which one and why.
- You can only write inside this folder, and you have no network access.
