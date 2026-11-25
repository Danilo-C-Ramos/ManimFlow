# ManimFlow design

Agreed on 2026-10-08 after a design interview. ManimFlow generalizes the workflow of a Minkowski-diagram project built with Manim and Claude Code for a special relativity course (Insper, 6th semester).

## 1. Goal

A tool a physics teacher can use day to day to make Manim animations for slides by chatting with a coding agent, without touching a terminal. The source is public and doubles as a portfolio piece. It is not a commercial product and does not need to stand out from existing tools.

## 2. What made the source project work

The relativity animations came out well because the Claude Code harness provided five things that a plain chat app does not:

1. **Closed render loop.** The agent wrote code, ran `manim`, looked at the PNG and fixed it.
2. **Project memory.** `CONTEXTO.md` held the rules (palette with measured contrast, decimal comma, "no equations inside the diagram") and the ideas the group had already rejected.
3. **Physics separated from drawing.** `relatividade.py` was the single source of truth, `analise.py` printed the answer key and `cenas.py` only drew from the `Cenario`.
4. **States and transitions.** The PNG of a state is the last frame of the transition into it, and continuity was checked with ffmpeg and numpy.
5. **Slide-ready output.** `render.sh` produced PNG, MP4 and GIF with a fixed palette.

ManimFlow packages these five things behind a UI.

## 3. Users and scope

- First user: one physics professor on Windows who already has Anaconda installed. ManimFlow must not touch that Anaconda.
- The core stays domain-agnostic: any Manim scene. Physics is the first rule set and the bundled example.
- UI and generated lesson content are in Brazilian Portuguese only. ManimFlow's code, docs and README are in English.
- Customization is kept to a minimum.

Non-goals for now: a hosted multi-user site, commercial distribution, app stores, voiceover, model fine-tuning.

## 4. Constraints found during research (October 2026)

- **Claude subscriptions cannot be used.** Since February 2026, Anthropic forbids using Free/Pro/Max OAuth tokens in third-party apps, including through the Agent SDK. Claude would only be reachable with an API key.
- **Sign in with ChatGPT requires a local app.** Plan usage is open to open-source projects and personal projects that run locally; hosted apps need the waitlist. The redirect must be a loopback URL (`http://127.0.0.1:<port>/...`). Eligible plans: Plus and Pro.
- **The Codex harness is embeddable.** `pip install openai-codex` installs the official Python SDK for the Codex app-server and pulls the CLI binary through `openai-codex-cli-bin` (Windows wheels available). Login supports ChatGPT in the browser, device code and API key.
- **Free hosting is gone or awkward.** Hugging Face Spaces with Gradio or Docker now requires PRO; free accounts get static Spaces only. Colab runs Manim but reinstalls LaTeX every session. Codespaces gives personal accounts 120 core-hours per month.
- **Windows needs no compiler.** Every Python dependency ships Windows wheels: `manim` (pure Python), `pycairo`, `manimpango`, `av`, `nicegui`, `openai-codex-cli-bin`, `pygit2`. `pycairo` has no macOS wheels, so macOS needs Homebrew or conda-forge.
- **LaTeX is the main install pain.** TinyTeX plus the package list from the Manim docs solves it per user, without admin rights.

## 5. Architecture

```
ManimFlow: one Python package, launched with `uvx manimflow`

  NiceGUI UI (browser at 127.0.0.1)
     │  user actions, agent events
  App core ── Agent (thin wrapper) ── openai-codex SDK ── Codex app-server (bundled binary)
     │                                     │  shell, sandboxed to the lesson folder
     └──────────────► manimflow CLI ◄──────┘
                         │  preview, render, frames, check-continuity, export, doctor
                      Manim CE + TinyTeX + PyAV (ffmpeg)

  Lesson folders on disk (<Documents>/Aulas Manim/...), each with a local git repo (pygit2)
```

The main seam is the `manimflow` CLI. The agent calls it through its shell, and the UI calls it from the export button. Nothing else talks to Manim directly.

## 6. Decisions

### 6.1 Auth and model

- Primary login: Sign in with ChatGPT through the browser loopback flow. Secondary: API key.
- Model and reasoning effort come predefined. A "Rápido / Caprichado" toggle switches between two presets. A discreet "Avançado" option lets the user pick model and effort by hand.
- The UI shows how much of the ChatGPT plan quota has been used.

### 6.2 Agent engine

- Codex app-server, driven by the `openai-codex` Python SDK.
- Wrapped behind a thin `Agent` interface, so the engine can later be swapped (own loop, ACP client) without touching the UI.
- Sandbox: `workspace_write` scoped to the lesson folder, network off, and no approval prompts for commands inside the folder.
- ManimFlow runs Codex in its own Codex home, apart from any Codex the teacher installed. See [ADR 0001](adr/0001-manimflow-has-its-own-codex-home.md).
- If the agent needs a new Python package, it stops and tells the user. Needing new libraries is a sign it is on the wrong path.

### 6.3 UI

- **NiceGUI.** The interface is written in Python and rendered in the browser with Vue/Quasar components. The server keeps a websocket open, so agent events and finished renders update the page without rerunning anything. Components used: `ui.chat_message`, `ui.codemirror`, `ui.video`, splitters, tabs.
- **Delivery.** In v0.1, `uvx manimflow` opens the app in the browser. In v0.2, a one-line installer adds a desktop shortcut. A packaged `.exe` comes only if the one-liner proves insufficient; NiceGUI's native mode and `nicegui-pack` make that possible.
- **Rebuilt after** the "ChatGPT with Projects" prototype (`prototypes/ui-chatgpt/` on `main`): a sidebar that maps the work (what needs the teacher, turmas with their lessons and a status each), a home that starts a lesson from a message, a page per turma, and a lesson screen with the chat beside a resizable, closable workspace. Turmas are [ADR 0004](adr/0004-lessons-are-grouped-in-turmas.md). See [lessons](lessons.md) and [the lesson screen](lesson-screen.md). The sketches below are the first version's.
- **Home ("Minhas aulas").** Lesson cards and a prominent "+ Nova aula" button. The bundled example sits in a separate strip below, so it never mixes with the teacher's lessons. Lessons live in `<Documents>/Aulas Manim` by default, and the location can be changed.

```
┌──────────────────────────────────────────────────────────┐
│  Minhas aulas                          [ + Nova aula ]   │
│                                                          │
│  ┌───────────────┐  ┌───────────────┐                    │
│  │ Aula 09       │  │ Aula 10       │                    │
│  │ Minkowski     │  │ Gêmeos        │                    │
│  │ editada ontem │  │ 3 estados     │                    │
│  └───────────────┘  └───────────────┘                    │
│ ──────────────────────────────────────────────────────── │
│  Exemplo · Relatividade: herói e espelho     [ abrir ]   │
└──────────────────────────────────────────────────────────┘
```

- **Lesson screen.** The lesson list, a chat with live agent events, plan cards that later become the timeline, a preview (video and states), editable code with a "Renderizar" button, the equations panel and export.

```
┌ Aulas ──────┬ Chat ─────────────────────┬ Prévia ─────────────────────────┐
│ Aula 09  ●  │ prof: mostre os eixos do  │ [ ▶  S1 → S2 ]                  │
│ Aula 10     │       herói se fechando   │ estados:  S0  S1 [S2] S3        │
│ + nova aula │ agente: editei cenas.py,  ├ Código │ Equações │ Exportar ───┤
│             │   renderizei e conferi a  │ γ = 1/√(1 − v²)    = 1,25       │
│ ⚙ perfil    │   continuidade ✓          │ x_H = γ(x_T − v t_T)            │
│             │ > _______________________ │                                 │
└─────────────┴───────────────────────────┴─────────────────────────────────┘
```

### 6.4 A lesson is a folder

```
Aulas Manim/
  perfil.md                  teacher-wide preferences (palette, fonts, decimal comma, slide background)
  Aula 09 - Minkowski/
    CONTEXTO.md              rules and decisions for this lesson, maintained by the agent
    plano.yaml               states and transitions; validated by the CLI, drawn as cards
    fisica.py                physics only; exposes equacoes()
    cenas.py                 drawing only, derived from fisica.py
    test_fisica.py           maintained by the agent
    saida/                   png/, mp4/ from render; powerpoint/, web/, beamer/, video/ from export
    .git/                    local only, managed by ManimFlow
```

File names inside a lesson are in Portuguese because the teacher reads them. The teacher can open the folder without ManimFlow, and the code belongs to them.

### 6.5 Plan before code

- For a new lesson, the agent first writes `plano.yaml`: states S0..Sn, what each one shows, and what each transition does with its approximate duration. Until the first approval, ManimFlow asks for the plan in a fixed format and writes the file itself ([the plan turn](plan.md#the-plan-turn)).
- The UI draws the plan as cards. The teacher edits text inline, comments on individual cards and presses "Aprovar plano", which sends all the feedback to the agent in one message.
- After rendering, each card gains the PNG thumbnail of its state, and the cards become the timeline.
- Small requests ("muda a cor da luz") skip the plan.
- The idea comes from the `manim-composer` skill in Generative Manim's skills comparison.

```
┌ Plano · Aula 09 ─────────────────────────────────────── [ Aprovar plano ] ┐
│ ┌ S0 ──────────────┐      ┌ S1 ──────────────┐      ┌ S2 ──────────────┐   │
│ │ Eixos da Terra,  │ ~4 s │ Eixos do herói   │ ~5 s │ Luz até o        │   │
│ │ herói na origem  │ ───► │ fecham até v=0,6 │ ───► │ espelho; (8, 8)  │   │
│ │ 💬 1 comentário  │      │ 💬 —             │      │ 💬 —             │   │
│ └──────────────────┘      └──────────────────┘      └──────────────────┘   │
│ [ + estado ]                                                               │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.6 Agent self-check loop

- After each change, the agent:
  - renders a low-quality preview (`-ql`);
  - extracts the first, middle and last frame of every transition that changed;
  - runs the numeric continuity check: the state PNG, the last frame of the incoming transition and the first frame of the outgoing one must match. The source project's threshold was under 0.1% of pixels with a channel difference above 60;
  - looks at the frames.
- At most 4 automatic attempts per request. If it still is not right, the agent shows what it has and says what is missing.
- High quality is rendered only on export.
- A lesson has one conversation, which every message continues and the server keeps while the app runs; `CONTEXTO.md` still holds the lesson's rules and decisions. See [ADR 0005](adr/0005-a-lesson-has-one-conversation.md), which replaced "every session starts a new thread".
- Manual code edits by the teacher are committed, and their diff goes to the agent with the next message.
- Generated code carries intent comments ("# este movimento mostra…").

### 6.7 Equations panel

- **Primary.** `fisica.py` exposes `equacoes()`, which returns a list of (name, LaTeX, value, unit). ManimFlow runs it and renders the result with KaTeX.
- **Secondary (v0.2).** During render, record every `MathTex`/`Tex` string that actually appears in each scene ("what the students will see"), so it can be compared with the physics list.

### 6.8 CLI

`manimflow` subcommands (names are indicative): `preview`, `render`, `frames`, `check-continuity`, `export`, `doctor`, `plan validate`. Scene names are validated as Python identifiers before they reach file paths or command arguments.

An agent skill or the lesson's agent instructions teach the agent when to use each subcommand.

### 6.9 Export

Each preset has editable fields:

| Preset | Output |
|---|---|
| PowerPoint | PNG per state + MP4 per transition |
| PowerPoint web / Google Slides | GIF with a fixed palette; the static GIF of a state is the last frame of its transition |
| Beamer / PDF | PNG per state |
| Whole-lesson video | all transitions concatenated (ffmpeg `concat`) |

Editable fields: resolution, fps, background and aspect ratio. Alpha channel output (MOV/WebM) and 4K come in v0.2. Details: `docs/export.md`.

### 6.10 Installation

- **Windows (the teacher).** `uv tool install manimflow` creates an isolated environment and leaves Anaconda untouched. Then `manimflow doctor --install` puts TinyTeX and Manim's LaTeX packages into a user folder, without admin rights.
- **One-line installer (v0.2).** `install.ps1` / `install.sh` installs uv, runs `uv tool install` and `doctor --install`, and creates a shortcut (`.lnk`, a minimal `.app`, or `.desktop`). Updates run `uv tool upgrade`; `--uninstall` removes everything.
- **macOS and Linux.** Documented separately in `docs/install-macos-linux.md`, using pixi: conda-forge binaries, no Homebrew, no admin.
- The README also keeps the manual steps.
- Docker and devcontainer come later.

### 6.11 Versioning ("hidden git")

- Each lesson folder is a local git repo managed through `pygit2`. There is no Git install and no GitHub account involved, and nothing leaves the machine.
- One commit per agent request and per manual edit followed by a render, with messages in Portuguese.
- The history provides the diff of manual edits for the agent, and undo. v0.2 adds a "voltar versão" button.

### 6.12 Testing

- **Per lesson.** The agent maintains `test_fisica.py`, which checks the values returned by `equacoes()`, and runs it on every change.
- **ManimFlow itself.** pytest for the CLI (render, frames, continuity, export, doctor) in GitHub Actions.
- **Later.** A small agent benchmark with 5 to 10 typical teacher requests, scored on render success, required code patterns and animation count with pass@k, modeled on Generative Manim's benchmark.

### 6.13 Hosting

Deferred. If it ever happens, a hosted site would use API keys only, since hosted Sign in with ChatGPT needs the waitlist. The other route is Codespaces on the teacher's own account with device-code login.

### 6.14 License

MIT. Any file copied from Generative Manim (Apache-2.0) keeps its Apache notice.

## 7. What we take from Generative Manim

Generative Manim (Apache-2.0) is the closest open-source prior art. Its commercial desktop app, Animo, is closed.

**Taken:**
- Preview as an agent tool (`get_preview` renders `-ql` PNGs and feeds frames back), with a cap on automatic iterations (they use 4).
- A per-conversation image budget.
- Project scene list in the agent context (our `CONTEXTO.md` and `plano.yaml` go further).
- User-defined rules (our `perfil.md`).
- Scene names validated as identifiers before reaching the CLI or file paths.
- Whole-video export with the ffmpeg `concat` filter, and aspect ratio through `frame_size`/`frame_width`.
- The benchmark design, where the renderer serves as a deterministic verifier.
- Planning before coding (`manim-composer`) and one-claim-per-scene thinking.
- Intent comments in generated code.

**Not taken:**
- One code path per LLM provider (Codex covers this).
- Code as a single `GenScene` blob in chat (we use files in a lesson folder).
- A 200-line documentation link index pasted into the prompt (the agent can read the installed Manim).
- Cloud storage, the fine-tuning pipeline, voiceover, and the "friendly persona" prompt.

## 8. Roadmap

**v0.1: real use by the teacher**

1. `uvx manimflow` and `doctor` (checks and installs LaTeX).
2. Login with ChatGPT or API key; model presets with a discreet "Avançado"; quota indicator.
3. "Minhas aulas" home, new lesson, bundled relativity example.
4. Lesson folder structure (`perfil.md`, `CONTEXTO.md`, `plano.yaml`, `fisica.py`, `cenas.py`, `saida/`) with local git and one commit per request.
5. Plan cards with comments and "Aprovar plano".
6. Chat with live agent events; a new thread per session.
7. CLI: preview, final render, frame extraction, continuity check, export with editable presets (resolution, fps, background).
8. Automatic self-check loop: up to 4 attempts, 3 frames per transition.
9. Panels: preview (video and states), editable code with "Renderizar" and diff to the agent, equations from `equacoes()`.
10. `test_fisica.py` maintained by the agent; CLI pytest in GitHub Actions.

Build order: a vertical slice first, on the bundled example lesson (CLI render/frames/continuity → agent wrapper and chat → preview panel). Then the home screen, plan cards, equations, export presets, `doctor` and login polish.

**v0.2:** one-line installer with a shortcut, `MathTex` capture, "voltar versão", alpha output and 4K.

**v0.3 and later:** agent benchmark, Docker/Codespaces, device-code login, hosted site with API keys, an MCP server over the CLI, lesson templates, possible contributions to Generative Manim.

## 9. To verify during implementation

- Which Codex models and reasoning efforts are available on Plus and Pro plans.
- Whether the app-server's rate-limit data is enough for the quota indicator.
- That Codex's `workspace_write` sandbox keeps `.git` read-only for the agent on Windows.
- KaTeX rendering inside NiceGUI.
- `manimflow` was free on PyPI as of 2026-10-08.

## References

- [Anthropic bans subscription OAuth in third-party apps](https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/)
- [Sign in with ChatGPT: registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Sign in with ChatGPT in open-source apps (OpenAI Cookbook)](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)
- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Codex Python SDK](https://github.com/openai/codex/tree/main/sdk/python)
- [T3 Code architecture (GUI over the Codex app-server)](https://www.mintlify.com/pingdotgg/t3code/concepts/architecture)
- [NiceGUI configuration and deployment](https://nicegui.io/documentation/section_configuration_deployment)
- [Manim installation with uv](https://docs.manim.community/en/stable/installation/uv.html)
- [Generative Manim](https://github.com/marcelo-earth/generative-manim)
- [Hugging Face pricing in 2026](https://www.eesel.ai/blog/hugging-face-pricing)
- [GitHub Codespaces billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)
