# Prototype: ManimFlow as "ChatGPT with Projects"

Throwaway. Open `index.html` in a browser. Two variants, switched with the pink bar
(bottom right), the ← → keys, or `?variant=F|C`. `?screen=` jumps to a screen: `home`,
`project`, `plan` (lesson waiting for approval), `rendering`, `code`, `eq`, `closed`
(preview closed), `wide` (preview enlarged), `export`, `palette`, `pin`, `settings`.

Everything is fake: the "render" is an SVG of the relativity example, a message plays a
canned agent turn, and nothing is saved. Round 1 (variants A and B) is in `v1-a-b.html`.

## Round 1 verdict

B's lesson screen and B's course page won. On top of that: the preview has to resize
with the mouse and close completely.

## F · Final (round 1 merged)

- **Lesson screen from B**: chat on the left, preview workspace on the right, filmstrip
  of states and transitions under the stage.
- **Resizable**: drag the bar between chat and preview; a double click resets it. ⊞ and ⊟
  jump to a bigger or smaller preview. The stage grows with the width and never gets
  taller than the window.
- **Closable**: ✕ closes the workspace, and the chat takes the whole page like ChatGPT.
  "◧ Mostrar prévia" in the top bar brings it back, and so does any card in the chat
  (preview, plan, code change).
- **Course page from B**: thumbnail grid, a "Nova aula" card, instructions on the side.
- **Home from A, with B's grid under it**: "O que vamos animar hoje?", a message box with
  a course picker, then the course cards.
- **Chat cards from A**: one collapsible activity block per turn, the plan inline, result
  cards that open the right tab.

## C · Colorido (new ideas)

Same base as F. It adds color and more of the Mobbin references:

| Idea | Where | Reference |
|---|---|---|
| **The sidebar maps the work instead of the chat history.** A "Precisa de você" inbox at the top (plan to approve, rendering, export ready), then courses as a tree with a status dot on each lesson (amber = plan waiting, spinner = rendering, green = ready, violet = exported) | Sidebar | Your feedback; MagicPath's files and favorites |
| **Quick actions on hover**: on a course `＋ aula`, `✎ instruções`, `⋯` (rename, color, open folder, archive the semester); on a lesson `▶ prévia`, `⇩ exportar`, `⋯` | Sidebar, lesson cards | MagicPath, Obvious |
| **Command palette** (Ctrl K): actions ("Exportar Minkowski para PowerPoint", "Nova aula em…") and lessons with their status | Everywhere | — |
| **Course page with a color band**: counts (lessons, ready, to approve), a message box to start a lesson, lessons grouped by stage (Precisa de você / Em produção / Prontas), and Instruções and Exportações tabs | Course page | Obvious, Ferndesk |
| **Home as a dashboard**: greeting, message box, "Precisa de você", "Continuar de onde parou" | Home | Obvious ("Ready to work on…") |
| **Vertical state list** next to the stage, transitions as ▶ buttons between states | Preview | Synthesia (scene list) |
| **Proportional timeline**: each transition is a block as wide as its duration, cuts are hatched, and a fill shows the playhead | Preview | Synthesia, Descript |
| **Comment on the image**: "📍 Comentar na imagem", click a spot, type. The pin goes with the next message and turns green when the agent resolves it | Preview, message box | Synthesia comments |
| **Approve in the message box**: when a plan is waiting, the box shows "O plano está esperando você · Aprovar plano" | Message box | Descript |
| **Suggestion chips** above the box: Mais devagar, Rótulos maiores, Trocar as cores… | Message box | AI Studio |
| **Saved version on every turn**, with "↺ Restaurar" | Chat | AI Studio checkpoints |
| **Live render status in the stage** while the agent works | Preview | Lindy |
| **Previous exports** in the export dialog and on the course page, with "Exportar de novo" | Export | Arcade |
| **Color**: flat blue accent, no gradients, one flat color per course (picked when the course is created), colored status pills | Everywhere | — |

## Recommendation

- **Ship F's structure.** It's what you chose, and it maps almost one to one onto NiceGUI.
- **From C, take these first**, because they change how the app works, not just how it
  looks: the sidebar as a map of the work with the inbox and status dots, quick actions on
  hover, approve in the message box, comments pinned on the image, and saved versions per
  turn.
- **Then the cheap color**: a color per course and status pills.
- **Leave for later**: the command palette, the dashboard home and the lessons grouped by
  stage. They pay off once a teacher has more than about ten lessons.

## What C implies beyond the UI

- **Lesson status is new state.** The sidebar needs to know when a plan is waiting,
  rendering is running, or an export has finished. Some of it can be read from the
  lesson folder (`plano.yaml` approved or not, `saida/` timestamps); "rendering" needs the
  running agent turn. That's a small `status(lesson)` function in `lessons.py`.
- **Pinned comments travel with the message**, the same way manual edits travel today
  (`edicoes-manuais.diff`): state, x/y as a fraction of the frame, text. The agent can
  render the frame with the pin drawn on it, so it knows what "este rótulo" means.
- **Turma is still a new domain level** (folder `Aulas Manim/<Turma>/<Aula>/` plus
  instructions per course). It needs a GLOSSARY entry and an ADR before code, plus a
  migration for lessons created without a course.

## Build order in NiceGUI (issue-sized)

1. **Shell**: `ui.left_drawer` sidebar, routes `/`, `/turma/<id>`, `/aula/<id>`, a global
   CSS file over Quasar's default look. Today's lesson screen goes inside unchanged.
2. **Turma** in `lessons.py` (ADR first) and the course page grid.
3. **Lesson workspace**: chat | drag bar | tabs, closable. `ui.splitter` gives the drag;
   the close button sets the splitter to 100 %. `PlanCards`, `PreviewPanel`, `CodeTab`
   and `EquationsPanel` move into the tabs; the filmstrip is new.
4. **Chat turns**: group `CommandStarted`/`CommandFinished`/`FileChanged`/`ImageViewed`
   into one block per turn, and add result cards.
5. **Message box**: Enter to send, Rápido/Caprichado chips (move `model_switch` here),
   approve-plan bar.
6. **Sidebar status and quick actions** (needs `status(lesson)`).
7. **Comments on the image**.
8. **Dialogs**: export with previous exports, settings with plan usage, new course.

Once the direction is settled, move this folder to a throwaway branch and link it from
the implementation issue. Only the decision belongs on `develop`.
