# The lesson screen

A lesson opens as a chat on the left and a workspace on the right, as in the "ChatGPT with Projects" prototype (`prototypes/ui-chatgpt/` on `main`, variant F with the parts of C its README picked). The code is in `src/manimflow/app.py`, with the preview in `preview.py` and the pinned comments in `pins.py`.

## Header

The turma (a link to its page) and the lesson's name, its status pill (see [lessons](lessons.md#status)), "Mostrar prévia" while the workspace is closed, and "Exportar", which opens the export dialog. On the example, "Restaurar exemplo" brings the original back, after a confirmation: its files and its conversation start over ([lessons](lessons.md#the-example)). Without the sidebar (in the tests), the settings gear sits here too.

## Chat and workspace

The bar between them drags to resize; a double click on it goes back to the default split. In the workspace's tab bar, the two arrows jump to a smaller or a bigger preview, and ✕ closes the workspace so the chat takes the whole page, centered like ChatGPT. "Mostrar prévia" brings it back, and so does any result card in the chat.

The workspace has four tabs: **Prévia**, **Plano** (the [plan cards](plan.md#plan-cards-in-the-app), side by side), **Código** ([the code tab](code-tab.md)) and **Equações**.

## Prévia

A stage shows one state's image or one transition's video. Under it, a filmstrip lists the states in plan order, each with its thumbnail, id and title, and between neighbouring states a ▶ pill with the transition's approximate duration. A click on a frame or a pill puts it on the stage; a transition's video starts playing. The panel looks at the lesson folder twice a second, and only redraws what changed, so a video on the stage keeps playing when another state is rendered.

**Comentar na imagem.** On a rendered state, this button turns the stage into a pin target: a click on the image asks for a note. The note shows as a chip in the message box ("📍 1 · S3: baixe um pouco este rótulo", with ✕ to drop it) and as a numbered orange pin on the image. It goes with the next message as the attachment `comentarios-na-imagem.md`: the state, the spot as a fraction of the frame's width and height from the top left, the note, and the path of a copy of the frame with the pin drawn on it (`.manimflow/comentarios/<n>-<state>.png`), which the agent looks at. Once that turn has run, the pin turns green and leaves the message box. A message that never reached the agent keeps its pins for the next one, as it keeps the manual edits.

## The conversation

A lesson has one conversation, which every message continues ([ADR 0005](adr/0005-a-lesson-has-one-conversation.md)). The chat shows it from the start each time the lesson opens; turns from Codex threads older than the newest one show above it, each from a line with its date. The conversation lives on the server: a turn goes on when the teacher opens another lesson, and coming back shows it where it is. Every tab open on the lesson shows the same conversation.

Above the chat, the lesson's stage: Plano › Sua aprovação › Animação › Pronta, read from the lesson's status. "Sua aprovação" is highlighted while the plan waits for the teacher.

On the example, an introduction written by the app (it spends no quota) heads the chat: what the lesson shows, that the copy is the teacher's to change, and three suggestions that fill the message box.

## A turn in the chat

The teacher's message shows as a bubble, with its pins under it. The agent's texts show in order, and the steps between two texts (commands, file changes, images it looked at) fold into one block. While the turn runs, the block's header names the current step, such as "Renderizando a prévia…"; when it ends, the number of steps and the turn's duration. Errors stay outside the blocks, in red.

While the turn runs, a bar above the message box says what the agent is doing now, in the teacher's words: "Lendo o plano e as cenas", "Escrevendo a física", "Renderizando a prévia", "Olhando a imagem S0-S1_fim.png", "Pensando". When the agent keeps a list of steps, the bar shows "Etapa 2 de 5" and the current one. It also shows how long the turn has run, and "Parar", which interrupts it.

After the turn, result cards say what it produced, each opening the tab that shows it:

- **Plano**, when the turn wrote a plan that isn't the placeholder: the states with what they show and the transitions' durations, and, while the plan waits for the teacher, "Aprovar e animar" and "Ver e editar os cartões";
- **Prévia atualizada**, when a `manimflow preview` or `render` succeeded: the newest image of each state;
- **Código alterado**, when `fisica.py` or `cenas.py` changed and nothing was rendered.

Turns from before the app started show smaller cards, without the plan's states or the images, which may have changed since.

Then, when the turn changed versioned files, a line "Versão salva às 14:32" (or "em 25/11 às 14:32" on another day) with **Restaurar**. After a confirmation, it brings the lesson's files back to how that turn left them, as a new version (see [versioning](versioning.md#restoring-a-version)). Renders stay as they are.

## The message box

Enter sends; Shift+Enter starts a new line. The "Rápido / Caprichado" switch picks the model preset from the next turn on ([models](models.md)). While the plan waits for the teacher, a bar above the text says "O plano está esperando a sua aprovação." with "Ver plano" (opens the Plano tab) and "Aprovar plano", which approves exactly as the button on the cards does.

Until the teacher first approves the plan, a message asks the agent for the plan in a fixed format ([the plan turn](plan.md#the-plan-turn)); "pode seguir" in the teacher's words approves it.

Every message also carries `contexto-da-aula.md`: the lesson's name, its turma, its status and its plan's states, and on the example that it is the bundled example the teacher is exploring.
