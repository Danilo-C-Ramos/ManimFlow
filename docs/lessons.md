# Lessons and the home screen

The app opens on "Minhas aulas", the home screen. It lists the teacher's lessons as cards and has a "+ Nova aula" button. The bundled example sits in its own strip below the cards. The code is in `src/manimflow/lessons.py` (the lesson store) and `src/manimflow/home.py` (the pages).

## The lessons folder

Lessons live in `<Documents>/Aulas Manim` by default. ManimFlow asks Windows for the Documents folder, since OneDrive may have moved it. On Linux it reads `XDG_DOCUMENTS_DIR` from `user-dirs.dirs` (`~/Documentos` on a Portuguese desktop) and falls back to `~/Documents`. The folder is created with the first lesson, not by opening the app.

"Mudar pasta" takes a full path, such as a synced folder, and creates it when it doesn't exist. Lessons already in the old folder stay where they are. The choice is kept in `config.json` in ManimFlow's own folder (`%LOCALAPPDATA%\ManimFlow` on Windows).

A lesson is any folder directly inside the lessons folder that has a `plano.yaml` or a `cenas.py`, so other folders the teacher keeps there are not listed. Each card shows:

- the lesson's name, which is its folder name;
- when one of its own files last changed (renders in `saida/` and the history in `.git/` don't count);
- the number of states in `plano.yaml`, left out when the plan can't be read.

The most recently edited lesson comes first.

## The teacher's profile

`perfil.md` sits in the lessons folder, one level above every lesson, and holds the preferences that every lesson follows: palette, fonts, decimal comma and slide background. The agent reads it as `../perfil.md`, and the equations panel looks in it for "vírgula decimal". "Perfil do professor" on the home screen shows it and saves it.

Until the teacher saves their own, the profile is the bundled example's. A new lesson writes that default next to itself when the folder has no profile yet. When the teacher moves to a folder without a profile, the current one is copied there.

## A new lesson

"+ Nova aula" asks for a name. The name becomes the folder name, so it must work on Windows: it can't be empty or longer than 80 characters, have any of `< > : " / \ | ? *`, start or end with a dot, or be a reserved name such as `CON`. It also can't be the name of a folder that already exists.

The lesson is built from the scaffold in `src/manimflow/modelo/`:

| File | Starts as |
|---|---|
| `CONTEXTO.md` | A note that the lesson is new and the plan is still to be agreed. |
| `plano.yaml` | One placeholder state, `S0`, so the plan is valid and the plan cards can draw it. |
| `cenas.py` | An empty scene, `S0_Inicio`, for the placeholder state. |
| `fisica.py` | `equacoes()` returning an empty list. |
| `test_fisica.py` | A test that compares `equacoes()` with an empty table of expected values. |
| `saida/` | Empty. |

Then the lesson gets its first version, `Primeira versão da aula` (see `docs/versioning.md`), and opens.

## The example

The bundled example (`src/manimflow/exemplos/relatividade`) is never opened in place. The first time it is needed, it is copied, with its own profile, to `exemplo/` in ManimFlow's own folder, and "Abrir o exemplo" opens that copy. The teacher can change the copy freely, and it is kept across launches with its version history and past sessions, like any lesson. The copy is outside the lessons folder, so it never shows among the teacher's lessons, and outside the temp folder, where Codex's Windows sandbox doesn't let the agent in (ADR 0003).

## The lesson list on the lesson screen

The lesson screen has a side column, as in the design's sketch: the teacher's lessons (most recently edited first, the open one in bold), the example below them, "+ Nova aula" and "Perfil do professor". Each entry opens that lesson, so the teacher can switch without going back to "Minhas aulas".

## Addresses

| Address | Page |
|---|---|
| `/` | Minhas aulas |
| `/aula/<name>` | The lesson with that folder name in the lessons folder |
| `/exemplo` | The copy of the example |

A name that isn't a lesson directly inside the lessons folder, such as `../other`, shows a "not in the lessons folder" page instead.
