# Working on a ManimFlow lesson

You work inside one lesson folder of ManimFlow, a tool a physics teacher uses to make Manim animations for slides. The teacher writes in Brazilian Portuguese and does not program.

- Before changing anything, read the teacher's profile (`../perfil.md`) and the lesson's `CONTEXTO.md`, and follow both. When the teacher settles a new rule or decision, record it in `CONTEXTO.md` so the next session knows it.
- Physics goes in `fisica.py` and drawing goes in `cenas.py`. `cenas.py` takes its numbers from `fisica.py` and computes no physics of its own.
- The teacher can also edit `fisica.py` and `cenas.py` by hand. When a message comes with the attachment `edicoes-manuais.diff`, it holds those edits since your last turn: build on them and never undo them unless the teacher asks.
- Render only through the `manimflow` CLI: `manimflow preview . <Scene>` while you work, and `manimflow render . <Scene>` only when the teacher asks for the final version. Never call `manim` directly.
- Write everything the teacher reads in Brazilian Portuguese: your replies, `CONTEXTO.md`, `plano.yaml`, code comments and the text inside the scenes.
- Never install packages with pip, conda, uv or anything else. If the work seems to need a new library, stop and tell the teacher which one and why.
- You can only write inside this folder, and you have no network access.
