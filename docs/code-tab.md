# The code tab

The lesson screen's "Código" tab shows `fisica.py` and `cenas.py` in a CodeMirror editor with Python highlighting. The teacher can fix a sign or a factor there without asking the agent. The code is in `src/manimflow/code_tab.py`.

## "Renderizar"

1. Every file with unsaved edits is written, then committed as `Edição manual em fisica.py` (or `em fisica.py e cenas.py`). See [versioning](versioning.md).
2. Every scene in the plan is previewed, in plan order, through `manimflow preview <lesson> <scene> --json`, the same CLI the agent uses. A change to `fisica.py` can affect any scene, so all of them are rendered. The first scene that fails stops the run, and the tab shows `A cena S2 não renderizou:` followed by the last line of Manim's output, which is the Python error.
3. The preview panel picks the new renders up on its own.

When the commit fails (say, a `.git/index.lock` left behind by a crash), the tab says so and still renders: the files are saved, and the next commit picks them up.

The button is disabled while the agent is working. A commit in the middle of a turn would take the agent's half-done changes for the teacher's, and the teacher's edit would then miss the next diff.

## Changes made outside the editor

The tab checks both files twice a second. When the agent (or another editor) changes a file:

- if the teacher has no unsaved edits in it, the editor loads the new version;
- otherwise the editor keeps the teacher's text and shows a warning with two choices: "Manter as minhas edições" (the next "Renderizar" writes the teacher's version over the new one) or "Carregar a versão nova" (the teacher's unsaved edits are dropped). "Renderizar" stays disabled until the teacher picks one.

## The diff to the agent

Before each message, the chat writes `History.manual_changes()` to `.manimflow/edicoes-manuais.diff` and sends that file as an attachment (the agent interface takes attachments as file paths). The folder is not versioned. Once the agent's turn ends, the diff starts over, so each edit reaches the agent once. Unsaved edits in the editor are not part of it. The agent instructions tell the agent to build on these edits and never undo them unless the teacher asks.

When the diff can't be read, the message still goes, and the chat says the edits could not be sent.
