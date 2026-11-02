# Models and quota

The lesson screen has a "Rápido / Caprichado" switch. Both positions use the same model at two reasoning efforts:

| Switch | Model | Effort |
|---|---|---|
| Rápido (default) | `gpt-6.1-sol` | `low` |
| Caprichado | `gpt-6.1-sol` | `high` |

The values live in `src/manimflow/model_presets.py`.

## Why these

On 2026-10-27 the Codex app-server (`openai-codex` 0.162) offered a ChatGPT Plus account eight models. A Pro account wasn't checked; Pro plans include what Plus has. `gpt-6.1-sol` was first in the list and was the catalog's default, with `low` as its default effort, so Rápido is what Codex itself would pick for a Plus account. The model accepts `low`, `medium`, `high`, `xhigh`, `max` and `ultra`.

Caprichado uses `high` rather than `xhigh` or `max`. Each agent turn runs several renders and checks, and the higher efforts would spend a Plus plan's 5-hour limit much faster. The rarer efforts stay one step away, in "Avançado".

`tests/test_codex_agent.py` checks that the model list offers both presets. When OpenAI retires the model, update `model_presets.py` and this page.

## Avançado

The settings dialog (the gear in the lesson header) has an "Avançado" section. It lists the models the account's catalog shows, without the hidden ones, and the efforts each one accepts. When a model doesn't accept the current effort, the effort switches to the model's default. A choice that matches a preset moves the switch to that preset. Any other choice leaves the switch on neither.

Settings apply from the next turn on, in every open session. They are not saved: the app starts on Rápido every time.

## Quota

The settings dialog shows how much of the ChatGPT plan is used. The data comes from the app-server's `account/rateLimits/read`, which reports a short window (5 hours on Plus) and a weekly one, each with the percent used and when it resets. The dialog reads it fresh each time it opens.

API keys have no plan quota, and the app-server refuses the request for them, so the dialog shows no usage then.

## Account

The dialog shows how the teacher signed in (ChatGPT with the account's email, or an API key) and has a "Sair" button. Signing out deletes `auth.json` from ManimFlow's Codex home (see [ADR 0001](adr/0001-manimflow-has-its-own-codex-home.md)) and brings back the sign-in screen.
