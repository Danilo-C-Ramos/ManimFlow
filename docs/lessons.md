# Lessons, turmas and the home screen

The app opens on the home screen: "O que vamos animar hoje?", a message box that starts a lesson, the turmas as cards, the lessons without a turma and the example. A sidebar on every page maps the teacher's work. The code is in `src/manimflow/lessons.py` (the lesson store), `src/manimflow/home.py` (the pages), `src/manimflow/sidebar.py` and `src/manimflow/dialogs.py`. The layout comes from the "ChatGPT with Projects" prototype (`prototypes/ui-chatgpt/` on `main`).

## The lessons folder

Lessons live in `<Documents>/Aulas Manim` by default. ManimFlow asks Windows for the Documents folder, since OneDrive may have moved it. On Linux it reads `XDG_DOCUMENTS_DIR` from `user-dirs.dirs` (`~/Documentos` on a Portuguese desktop) and falls back to `~/Documents`. The folder is created with the first lesson or turma, not by opening the app.

"Mudar pasta", at the bottom of the home screen, takes a full path, such as a synced folder, and creates it when it doesn't exist. Lessons already in the old folder stay where they are. The choice is kept in `config.json` in ManimFlow's own folder (`%LOCALAPPDATA%\ManimFlow` on Windows).

```
Aulas Manim/
  perfil.md                     the teacher's profile
  Relatividade Restrita/        a turma
    turma.md                    its instructions
    .turma.json                 its color
    Aula 09 - Minkowski/        a lesson
  Lançamento oblíquo/           a lesson without a turma
```

A lesson is any folder that has a `plano.yaml` or a `cenas.py`, directly inside the lessons folder or directly inside a turma. Other folders the teacher keeps there are not listed.

## Turmas

A turma groups the lessons of one course, with instructions that hold for all of them (ADR 0004). It is a folder directly inside the lessons folder with a `turma.md`, which the agent reads as `../turma.md` after the profile and before the lesson's `CONTEXTO.md`. Turmas don't nest.

"+" next to "Turmas" in the sidebar, or "Nova turma" on the home screen, asks for a name and a color from a fixed palette of eight flat colors. The name follows the lesson name rules below. The color is kept in `.turma.json` inside the turma, so it moves with the folder; a turma without one gets a palette color from its name. "⋯ › Mudar a cor" changes it.

A turma's page has a band in its color with the number of lessons, how many are ready and how many wait for an approval, and a message box that starts a lesson in the turma. Below it are the lesson cards with a "+ Nova aula" card, and the turma's instructions on the side, with "Editar".

Lessons made before turmas stay directly in the lessons folder and show under "Sem turma". ManimFlow never moves a lesson: Codex finds a lesson's past conversations by its folder, so a moved lesson would lose them in the app.

## The teacher's profile

`perfil.md` sits in the lessons folder and holds the preferences that every lesson follows: palette, fonts, decimal comma and slide background. The agent reads it as `../perfil.md`, or `../../perfil.md` from a lesson inside a turma, and the equations panel looks in the same places for "vírgula decimal". "Perfil do professor", at the bottom of the sidebar, shows it and saves it.

Until the teacher saves their own, the profile is the bundled example's. A new lesson or turma writes that default when the folder has no profile yet. When the teacher moves to a folder without a profile, the current one is copied there.

## A new lesson

There are two ways to start one:

- **From a message.** The message box on the home screen (with a turma picker) or on a turma's page creates the lesson and opens it with the message already on its way to the agent. The lesson is named after the message's first words, up to 60 characters, without the characters Windows forbids, with " (2)" and up when the name is taken.
- **By name.** "Nova aula" at the top of the sidebar, "+" on a turma in the sidebar, or the "+ Nova aula" card on a turma's page ask for a name and, when there are turmas, which one.

The name becomes the folder name, so it must work on Windows: it can't be empty or longer than 80 characters, have any of `< > : " / \ | ? *`, start or end with a dot, or be a reserved name such as `CON`. It also can't be the name of a folder that already exists in the same place.

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

## Status

The sidebar and the lesson cards show where each lesson stands, read from its folder by `status()`:

| Status | When |
|---|---|
| Nova | The plan is still the scaffold's placeholder, or can't be read. |
| Plano para aprovar | The plan isn't the one the teacher last approved, and nothing was rendered since it changed: the agent wrote it and stopped, or the teacher edited the cards. |
| Em produção | Some state has no image yet. |
| Pronta | Every state has an image. |
| Exportada | Ready, and an export is newer than the newest render. |

"Aprovar plano" records the plan as approved once its turn ends, as a digest in `.git/manimflow-plano-aprovado`. The example's copy is approved when it is made. While the agent works on a lesson, renders from the code tab, or an export runs, the status shows "Trabalhando" with a spinner instead; that part comes from the running app, not the folder (`activity.py`).

## The sidebar

From top to bottom:

- "ManimFlow" (back to the home screen), the settings gear, and "Nova aula".
- **Precisa de você**: lessons whose plan waits for approval, lessons the agent is working on, and exports finished in this session that the teacher hasn't opened. A click opens the lesson on the right tab, or the export's folder.
- **Turmas**, as a tree: each turma with its color and number of lessons, and its lessons with a status dot. The open lesson's turma starts unfolded. On hover, a turma offers "+" (new lesson in it), "✎" (its instructions) and "⋯" (change the color, open the folder); a lesson offers "▶" (the preview), "⇩" (the export dialog) and "⋯" (open the folder).
- **Sem turma**, when there are lessons without a turma, and **Exemplo**.
- The ChatGPT plan's usage, which opens the settings, and "Perfil do professor". When nobody is signed in, "Entrar com o ChatGPT" takes the usage's place, and the settings offer both ways to sign in instead of the account.

The sidebar looks at the lessons folder every two seconds, so it follows what the agent does in another tab.

## The example

The bundled example (`src/manimflow/exemplos/relatividade`) is never opened in place. The first time it is needed, it is copied, with its own profile, to `exemplo/` in ManimFlow's own folder, and "Abrir o exemplo" or "Herói e espelho" in the sidebar opens that copy. The teacher can change the copy freely, and it is kept across launches with its version history and its conversation, like any lesson. The copy is outside the lessons folder, so it never shows among the teacher's lessons, and outside the temp folder, where Codex's Windows sandbox doesn't let the agent in (ADR 0003).

The example comes with a preview of every scene (`saida/previa/`, about 1.4 MB), so it shows its images and videos at once, before LaTeX is even installed. A copy made before the previews came with the example gets the ones it lacks when it opens; a render of the teacher's own is newer, and the preview shows the newest.

Its chat is for exploring and changing the example: the app introduces it, and each message tells the agent that this is the bundled example ([the lesson screen](lesson-screen.md#the-conversation)). "Restaurar exemplo" in its header copies the original over the teacher's copy, with a new history, and puts its conversation away.

## Addresses

| Address | Page |
|---|---|
| `/` | The home screen |
| `/turma/<turma>` | A turma's page |
| `/aula/<turma>/<aula>` | A lesson inside a turma |
| `/aula/<aula>` | A lesson without a turma |
| `/exemplo` | The copy of the example |

A lesson address also takes `?aba=Prévia` (or `Plano`, `Código`, `Equações`) to open on that tab, and `?exportar=1` to open the export dialog. An address that isn't a lesson or turma inside the lessons folder, such as `../other`, shows a "not in the lessons folder" page instead.
