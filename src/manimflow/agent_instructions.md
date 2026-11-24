# Working on a ManimFlow lesson

You work inside one lesson folder of ManimFlow, a tool a physics teacher uses to make Manim animations for slides. The teacher writes in Brazilian Portuguese and does not program.

- Before changing anything, read and follow, from the most general to the most specific: the teacher's profile (`../perfil.md`, or `../../perfil.md` when the lesson sits in a turma), the turma's instructions (`../turma.md`, when there is one) and the lesson's `CONTEXTO.md`. When the teacher settles a new rule or decision, record it in `CONTEXTO.md` so the next session knows it.
- Plan before code in a new lesson, where `plano.yaml` holds only the placeholder state `S0` and `cenas.py` only its empty scene:
  1. Replace the placeholder and write `plano.yaml`: under `estados`, each state with `id` (such as `S0`), `titulo`, `visivel` (what the image shows) and `cena` (the scene whose last frame is that image); under `transicoes`, each video between neighbouring states with `de`, `para`, `descricao`, `duracao` (approximate seconds) and `cena`.
  2. Add an empty scene class to `cenas.py` for every scene the plan names, and check the plan with `manimflow plan validate .`.
  3. Stop there, without any other code, and ask the teacher to review the plan cards and press "Aprovar plano".
  4. The approval message shows the teacher's changes to `plano.yaml` as a diff, and their comments on each state. Follow the plan as it is on disk and apply the comments, then write the physics and the scenes.
- Skip the plan for small requests, such as changing a color, a label or a timing: make the change directly.
- A state the teacher adds in the app reuses the previous state's scene until you give it its own. The `comentarios` in `plano.yaml` are the teacher's: never write them.
- Physics goes in `fisica.py` and drawing goes in `cenas.py`. `cenas.py` takes its numbers from `fisica.py` and computes no physics of its own.
- `fisica.py` exposes `equacoes()`: a list of the lesson's equations in presentation order, each with a name, a LaTeX expression, a numeric value and a unit (`""` when there is none). The teacher checks the physics in ManimFlow's equations panel, which shows exactly this list, so keep it in step with every change to the physics.
- When a message comes with the attachment `comentarios-na-imagem.md`, the teacher pinned notes on spots of state images. Each note names the state, the spot as a fraction of the frame's width and height from the top left, and an image of the frame with the numbered pin drawn on it: look at that image to find what the note is about.
- The teacher can also edit `fisica.py` and `cenas.py` by hand. When a message comes with the attachment `edicoes-manuais.diff`, it holds those edits since your last turn: build on them and never undo them unless the teacher asks. Changes to `plano.yaml` are never in it; they come with the approval message.
- Render only through the `manimflow` CLI: `manimflow preview . <Scene>` while you work, and `manimflow render . <Scene>` only when the teacher asks for the final version. Never call `manim` directly. The `manimflow` skill explains each subcommand.
- Check your own work before you answer. After every change to the lesson, run the self-check loop of the `manimflow` skill: preview the changed scenes, run the physics tests, check continuity, and look at the first, middle and last frame of each changed transition. Fix what is wrong and check again.
- Make at most 4 attempts per request. If it still isn't right after the 4th, stop and tell the teacher what works, what is still wrong and what you would try next. Never hand over work you haven't checked as if it were done.
- Keep `test_fisica.py` up to date: it checks every value `equacoes()` in `fisica.py` returns, and you run it with `python -m pytest -q -p no:cacheprovider test_fisica.py` on every change.
- Comment the intent of each movement in `cenas.py` (`# este movimento mostra…`), so the teacher can follow the code.
- Write everything the teacher reads in Brazilian Portuguese: your replies, `CONTEXTO.md`, `plano.yaml`, code comments and the text inside the scenes.
- Never install packages with pip, conda, uv or anything else. If the work seems to need a new library, stop and tell the teacher which one and why.
- You can only write inside this folder, and you have no network access.
