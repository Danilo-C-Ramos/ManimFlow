# Lesson versioning

Each lesson folder is a local git repository (`.git/` inside the lesson), managed by ManimFlow through pygit2. The teacher needs no Git install and no account, and nothing is pushed anywhere. The code is in `src/manimflow/versioning.py`.

## When a version is saved

| When | Commit message |
|---|---|
| A lesson without history is opened | `Primeira versão da aula` |
| The teacher's files changed outside ManimFlow before a message to the agent | `Edições feitas fora do ManimFlow` |
| An agent turn ends, even a failed one, and it changed files | `Pedido: <the teacher's message>`, or `Pedido: Aprovei o plano` for an approval |
| The teacher edits code in the app and presses "Renderizar" | `Edição manual em fisica.py` |
| The teacher edited the plan cards, before a message to the agent | `Edição manual em plano.yaml` |
| An approval's turn ends well, and its comments leave the plan | `Comentários do plano atendidos` |

A turn or an edit that changes no file makes no commit. Each commit is a full snapshot of the lesson, so deleted files leave it too. The teacher's edits in the app commit only the files they changed, so the code tab and the plan cards never take each other's edits, nor ones made outside ManimFlow. A message that never reached the agent (Codex refuses the turn when its sandbox can't start) commits nothing. When a commit fails (say, a `.git/index.lock` left behind by a crash), the chat says so in Portuguese and goes on, and the next commit picks the changes up.

## What is not versioned

Everything a render or a test run can reproduce:

- `saida/`: previews, final renders and exports;
- `.manimflow/`: staging and Manim's cache;
- `media/`: where Manim writes when run by hand;
- `__pycache__/`, `*.pyc` and `.pytest_cache/`.

The list is written to `.git/info/exclude` every time the lesson opens, rather than to a `.gitignore`, so the teacher's folder gets no extra file and older lessons pick up a changed list.

## The diff of manual edits

`History.manual_changes()` returns the teacher's changes since the agent's last turn, committed or not, as a unified diff with paths relative to the lesson (`a/fisica.py`, `b/fisica.py`). The agent's own changes are never in it, and neither is `plano.yaml`: its changes reach the agent through "Aprovar plano". It goes to the agent with the teacher's next message, as the attachment `.manimflow/edicoes-manuais.diff`, so the agent builds on the fix instead of overwriting it. See [the code tab](code-tab.md).

The agent's last turn is the ref `refs/manimflow/last-agent-turn`. Every turn moves it, including a turn that changed nothing, since that turn already received the diff with its message. A message that never reached the agent leaves it where it was, so the diff goes with the next one.

## Isolation from the teacher's Git

A teacher who also uses Git may have global settings (line endings, global ignores, diff prefixes) that would change what gets committed or how the diff reads. ManimFlow tells libgit2 not to read the system, XDG and global Git config, so only each lesson's own config applies. A lesson inside another repository (a synced folder under Git, say) still gets its own history, because ManimFlow never searches parent folders for a repository.
