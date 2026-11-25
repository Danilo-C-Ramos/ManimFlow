# Models and quota

The lesson screen has a "Rápido / Caprichado" switch. Both positions use the same model at two reasoning efforts, `low` and `high`. The model depends on the account:

| Account | Model |
|---|---|
| ChatGPT Plus, Pro, Business, Enterprise, Edu, and API keys | `gpt-6.2-sol`, else `gpt-6.1-sol` |
| ChatGPT Free and Go | `gpt-6-luna` |

ManimFlow only takes a model the account's catalog lists. When the catalog lists none of the account's models, the switch uses the catalog's own default, the model Codex itself would pick. When a model lacks `low` or `high`, that position uses the model's default effort.

The values and the choice live in `src/manimflow/model_presets.py`. The settings dialog shows the plan and which model the switch uses ("Rápido e Caprichado usam o GPT-6.2-Sol.").

## Why these

The app-server reads the account's plan (`account/read`, `planType`) and fetches the model catalog with the account's sign-in (`model/list`). The catalog also depends on the Codex version: on 2026-11-25 the same Plus account got no GPT-6.2 models through `openai-codex` 0.162, and got `gpt-6.2-sol` first, as the catalog's default, through 0.172. ManimFlow pins 0.172 for that reason.

- **Plus and up.** OpenAI's [pricing page](https://learn.chatgpt.com/docs/pricing) lists GPT-6.2 Sol on Plus, Pro, Business, Enterprise and Edu. Enterprise and Edu workspaces get it only once an administrator turns it on, so their catalog may lack it. `gpt-6.1-sol` is the fallback then. Its default effort is `low`, so Rápido is what Codex itself would pick.
- **Free and Go.** The same page gives Free and Go only "GPT-6 Luna at Standard speed", on Free "subject to rollout". A ChatGPT Free account that asked for `gpt-6.1-sol` got `model_not_found` with the subreason `model_not_in_accessible_catalog`. ManimFlow picks Luna from the plan even when the catalog lists more, since a refused turn costs the teacher a message.

Caprichado uses `high` rather than `xhigh` or `max`. Each agent turn runs several renders and checks, and the higher efforts would spend a plan's 5-hour limit much faster. The rarer efforts stay one step away, in "Avançado".

`tests/test_codex_agent.py` checks that the bundled catalog offers both plans' models at both efforts, and `tests/test_model_presets.py` covers the choice. When OpenAI retires a model, update `model_presets.py` and this page.

## Seeing what an account gets

`manimflow account` asks the app-server, with ManimFlow's own sign-in, for the plan, the catalog and the plan's usage, and prints which model the switch takes:

```
$ manimflow account
Conta: ChatGPT, plano plus (professora@example.com)
Rápido: gpt-6.2-sol, esforço low
Caprichado: gpt-6.2-sol, esforço high
Modelos do catálogo da conta (* o padrão do Codex):
  * gpt-6.2-sol    GPT-6.2-Sol: low, medium, high, xhigh, max, ultra (padrão low)
    gpt-6-luna     GPT-6-Luna: low, medium, high, xhigh, max (padrão medium)
    ...
Uso do plano: 0% (janela de 300 min, renova em 25/11 13:18)
```

`--json` prints the same as a JSON report. The command doesn't set up the sandbox and starts no turn, so it spends no quota. It fails when ManimFlow isn't signed in.

## Avançado

The settings dialog (the gear in the lesson header) has an "Avançado" section. It lists the models the account's catalog shows, without the hidden ones, and the efforts each one accepts. When a model doesn't accept the current effort, the effort switches to the model's default. A choice that matches a preset moves the switch to that preset. Any other choice leaves the switch on neither.

A model the plan doesn't include fails the turn with "O seu plano não inclui esse modelo. Escolha outro em Configurações, na parte "Avançado"."

Settings apply from the next turn on, in every open session. They are not saved: the app starts on Rápido every time. The switch keeps its position, and each turn reads it on the model of the account it runs with. Signing in or out drops a model picked in "Avançado", since the next account's plan may not include it.

## Quota

The settings dialog shows how much of the ChatGPT plan is used. The data comes from the app-server's `account/rateLimits/read`, which reports a short window (5 hours on Plus) and a weekly one, each with the percent used and when it resets. The dialog reads it fresh each time it opens.

API keys have no plan quota, and the app-server refuses the request for them, so the dialog shows no usage then.

## Account

The dialog shows how the teacher signed in (ChatGPT with the plan and the account's email, or an API key) and has a "Sair" button. Signing out deletes `auth.json` from ManimFlow's Codex home (see [ADR 0001](adr/0001-manimflow-has-its-own-codex-home.md)) and brings back the sign-in screen.
