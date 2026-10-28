# Working on a ManimFlow lesson

You work inside one lesson folder of ManimFlow, a tool a physics teacher uses to make Manim animations for slides. The teacher writes in Brazilian Portuguese and does not program.

- Before changing anything, read the teacher's profile (`../perfil.md`) and the lesson's `CONTEXTO.md`, and follow both. When the teacher settles a new rule or decision, record it in `CONTEXTO.md` so the next session knows it.
- Plan before code in a new lesson, one whose `plano.yaml` has no states yet:
  1. Write `plano.yaml`: under `estados`, each state with `id` (such as `S0`), `titulo`, `visivel` (what the image shows) and `cena` (the scene whose last frame is that image); under `transicoes`, each video between neighbouring states with `de`, `para`, `descricao`, `duracao` (approximate seconds) and `cena`.
  2. Add an empty scene class to `cenas.py` for every scene the plan names, and check the plan with `manimflow plan validate .`.
  3. Stop there, without any other code, and ask the teacher to review the plan cards and press "Aprovar plano".
  4. The approval message shows the teacher's changes to `plano.yaml` as a diff, and their comments on each state. Follow the plan as it is on disk and apply the comments, then write the physics and the scenes.
- Skip the plan for small requests, such as changing a color, a label or a timing: make the change directly.
- A state the teacher adds in the app reuses the previous state's scene until you give it its own. The `comentarios` in `plano.yaml` are the teacher's: never write them.
- Physics goes in `fisica.py` and drawing goes in `cenas.py`. `cenas.py` takes its numbers from `fisica.py` and computes no physics of its own.
- Render only through the `manimflow` CLI: `manimflow preview . <Scene>` while you work, and `manimflow render . <Scene>` only when the teacher asks for the final version. Never call `manim` directly.
- Write everything the teacher reads in Brazilian Portuguese: your replies, `CONTEXTO.md`, `plano.yaml`, code comments and the text inside the scenes.
- Never install packages with pip, conda, uv or anything else. If the work seems to need a new library, stop and tell the teacher which one and why.
- You can only write inside this folder, and you have no network access.
