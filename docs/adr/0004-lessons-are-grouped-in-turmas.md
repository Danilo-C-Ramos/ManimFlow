# Lessons are grouped in turmas, one folder level deep

A teacher makes lessons for several courses at once (Relatividade Restrita, Física 1), and each course has its own conventions: notation, level, the textbook's symbols. The UI rebuilt after the "ChatGPT with Projects" prototype (`prototypes/ui-chatgpt/` on `main`) puts courses in the sidebar, with the lessons under them. So ManimFlow needs a level above the lesson: the **turma**.

## Decision

- A turma is a folder directly inside the lessons folder that holds a `turma.md`. Its lessons are the lesson folders directly inside it: `Aulas Manim/<Turma>/<Aula>/`. Turmas don't nest.
- `turma.md` holds the turma's instructions, in the teacher's words. The agent reads it as `../turma.md`, after the teacher's profile and before the lesson's `CONTEXTO.md`. The rules apply from most general to most specific: profile, turma, lesson.
- The profile stays one per lessons folder, so inside a turma the agent reads it as `../../perfil.md`. The equations panel looks for it in both places.
- Each turma has one flat color, picked when it is created, from a fixed palette. The color lives in `.turma.json` in the turma folder, so it travels with the folder and the teacher never sees the file. A turma without one gets a palette color from its name.
- Lessons stay where they are. A lesson directly inside the lessons folder, made before turmas existed, is listed under "Sem turma" and works as before. Nothing is moved for the teacher.
- A lesson is named by its path inside the lessons folder (`Relatividade/Aula 09`), and its address is `/aula/<turma>/<aula>`, or `/aula/<aula>` without a turma.

## Why not move the old lessons into a turma

Codex finds a lesson's past conversations by the folder they started in. Moving a lesson folder, by ManimFlow or by hand, hides its past conversations from the app. The memory that matters is in `CONTEXTO.md` and the version history, which move with the folder, but a silent migration would still lose something the teacher didn't ask to lose. The same reason keeps "Renomear" and "Mover" out of the UI for now.

## Why a marker file

A folder of lesson folders could be taken for a turma by its content alone. But teachers keep other folders next to their lessons (old material, a "Rascunhos" folder), and listing those as turmas would be noise. `turma.md` is also the file the agent reads, so the marker carries the turma's meaning, not only its existence.

## Consequences

- `Library` lists turmas, the lessons in each one and the lessons without one. Lesson names are only unique inside their turma.
- The lesson's status (`Nova`, `Plano para aprovar`, `Em produção`, `Pronta`, `Exportada`) is read from its folder, for the sidebar and the cards. Whether the agent is working on it comes from the running app.
- The agent instructions name `../turma.md` and both places of the profile.
