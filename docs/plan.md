# The lesson plan (`plano.yaml`)

Each lesson folder has a `plano.yaml` that lists the lesson's states in slide order and the transitions between them. The agent writes it before any code, the UI draws it as cards, and `manimflow plan validate <lesson>` checks it. Keys are in Portuguese because the teacher reads the file.

```yaml
estados:
  - id: S0
    titulo: Diagrama da Terra
    visivel: Eixos da Terra, a linha da Terra em x = 8 e o herói na origem.
    cena: S0_Base
  - id: S1
    titulo: Eixos do herói
    visivel: Os eixos oblíquos do herói sobre os eixos da Terra.
    cena: S1_EixosHeroi
    comentarios:
      - Deixar a grade um pouco mais clara.

transicoes:
  - de: S0
    para: S1
    descricao: A grade e os eixos do herói aparecem e se fecham até v = 0,6.
    duracao: 4
    cena: S1_EixosHeroi
```

## States (`estados`, required)

An ordered list with at least one state. Each state is a static image on a slide.

| Key | Required | Meaning |
|---|---|---|
| `id` | yes | Unique id, such as `S0` or `S2b`. It follows the same rule as scene names (a plain ASCII Python identifier, not a Windows reserved name), because ids end up in exported file names. |
| `titulo` | yes | Short title for the card. |
| `visivel` | yes | What the image shows. |
| `cena` | yes | The scene class in `cenas.py` whose last frame is this state's image. For a state reached by a transition, this is usually the transition's own scene. |
| `comentarios` | no | The teacher's comments on this state, as a list of strings. |

## Transitions (`transicoes`, optional)

Each transition is a short video that starts on one state's image and ends on the next one's.

| Key | Required | Meaning |
|---|---|---|
| `de` | yes | Id of the state the video starts from. |
| `para` | yes | Id of the state it ends on. It must come right after `de` in `estados`. |
| `descricao` | yes | What happens in the video. |
| `duracao` | yes | Approximate length in seconds, a number greater than zero. |
| `cena` | yes | The scene class in `cenas.py` that animates it. |

Two neighbouring states without a transition between them are a plain slide change, with no video. A state can repeat an earlier image under a new id. In the bundled example, `S3v` shows the S3 image again so that the boost transition can start from it after the S5 detour.

## Validation

`manimflow plan validate <lesson> [--json]` exits non-zero when the plan has any of these problems. Each one gets its own message in Portuguese:

- the lesson folder or `plano.yaml` is missing, `plano.yaml` or `cenas.py` is not UTF-8, or `plano.yaml` is not valid YAML;
- `estados` is missing or empty;
- a state or transition lacks a required field, or a field has the wrong type;
- two states share an id, or an id is not a plain identifier;
- a transition names a state that is not in the plan, joins states that are not neighbours, or repeats a pair;
- a scene name is not a plain identifier, is not a class in `cenas.py`, or names a class that is not a scene.

Scenes are found by reading `cenas.py` without running it. A top-level class is a scene when one of its bases is named like a Manim scene (`Scene`, `MovingCameraScene`, ...) or is itself a scene in the same file, so `class S0_Base(Base)` with `class Base(Scene)` counts and a helper such as `class Janela` does not.

The JSON report has this shape:

```json
{
  "ok": false,
  "command": "plan validate",
  "lesson": "/path/to/Aula 09",
  "errors": ["Transição S0 → S2: S2 não vem logo depois de S0 no plano. Uma transição liga um estado ao seguinte."]
}
```
