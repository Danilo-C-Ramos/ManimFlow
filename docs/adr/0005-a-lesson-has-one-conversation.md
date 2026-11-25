# A lesson has one conversation, which the server keeps

The first design started a new Codex thread every time a lesson opened, with `CONTEXTO.md` as the memory between them, and kept the old threads readable under "Anteriores" (design 6.6). In use, it read as a chat that loses its messages: the teacher sends a request, opens another lesson, comes back, and the conversation is empty. "Nova" and "Anteriores" made it look like a lesson held several chats, when the teacher thinks of one lesson as one ongoing conversation about one animation.

The turn also lived in the page. Leaving a lesson in the middle of a turn destroyed the page the turn was still writing to, so the turn's last version could go unsaved and the lesson could stay "Trabalhando".

## Decision

- A lesson has one conversation: its newest Codex thread in which the teacher wrote, found by the lesson's folder. Opening the lesson resumes it, and every message continues it. The first message of a lesson starts it.
- The chat shows every turn of the lesson's threads, oldest first. Threads from before this decision show above the newest one, each from a line with its date. "Anteriores" and "Nova" are gone.
- The conversation lives on the server for as long as the app runs (`conversation.py`), not in the page. A turn runs to its end there, saves its version and keeps what it showed, whatever the pages do. Every page on the lesson follows the same conversation, and a page opened during a turn joins it.
- Each agent turn's version ends its commit message with `Turno: <id>`, so the chat finds the version of each past turn again after a relaunch.
- When the conversation outgrows the model's context and Codex can't shrink it, the next message starts a new thread. `CONTEXTO.md` still carries the lesson's rules and decisions. Read back from Codex, the chat marks where each thread begins.

## Consequences

- `Agent.session(lesson)` replaces `start_session`, and `Agent.lesson_history(lesson)` replaces the list of past sessions.
- The page asks the conversation to start a turn and shows the turns it is told about. Steps that must happen whatever the page does, such as recording an approved plan, run on the server once the turn ends. An approval in the teacher's words ("pode seguir") is the exception: the page that sent it starts the approval turn, so a teacher who leaves before the plan turn ends finds the plan still waiting.
- "Parar" holds also before the turn reaches the agent, while the thread starts or resumes.
- Restoring the example drops its conversation; the other tabs on it reload.
- The plan turn ([plan](../plan.md#the-plan-turn)) is one more turn of the same conversation, so the approval and the production turns after it see how the plan was agreed.
- A lesson folder moved by hand still loses its conversation in the app, as before (ADR 0004).
