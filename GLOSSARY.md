# Glossary

Terms as ManimFlow uses them, in code, docs and issues. Portuguese terms are the teacher's words and appear as-is in the UI.

| Term | Meaning | Avoid |
|---|---|---|
| **Aula** (lesson) | One folder with a plan, the physics, the scenes and their renders: what becomes one set of slides. | project, animation |
| **Turma** (course) | A folder of lessons for one course, with the teacher's instructions for that course in `turma.md`. See ADR 0004. | class (clashes with Python), project, folder |
| **Lessons folder** | `Aulas Manim/`, the folder that holds the turmas, the lessons without a turma and the profile. | workspace, library (that's the code's name for the store) |
| **Perfil do professor** (profile) | `perfil.md` in the lessons folder: preferences every lesson follows. | settings (those are ManimFlow's own) |
| **Plano** (plan) | `plano.yaml`: the states and transitions of a lesson, approved by the teacher before code. | storyboard, script |
| **Estado** (state) | One still image of the lesson, the last frame of the transition into it. | frame, slide |
| **Transição** (transition) | The video between two neighbouring states. | animation, clip |
| **Prévia** (preview) | A low-quality render the agent and the teacher check while working. | draft |
| **Exportação** (export) | The final-quality files for slides, written to `saida/<preset>/`. | build, publish |
| **Status** | Where a lesson stands: Nova, Plano para aprovar, Em produção, Pronta or Exportada, plus "the agent is working" while a turn runs. | state (that's a plan's image) |
| **Versão** (version) | A commit in the lesson's local history, one per agent turn and per manual edit. "Restaurar" brings the lesson's files back to one. | checkpoint, snapshot |
| **Comentário na imagem** (pin) | A note the teacher places on a spot of a state's image, sent with the next message. | annotation |
