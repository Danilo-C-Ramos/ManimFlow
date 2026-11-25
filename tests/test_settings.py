import asyncio
from contextlib import asynccontextmanager

from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AssistantText, ModelSettings
from manimflow.app import lesson_page
from manimflow.fake_agent import ScriptedAgent

# The scripted agent's account is on Plus, whose switch uses GPT-6.2-Sol.
QUICK = ModelSettings("gpt-6.2-sol", "low")
CAREFUL = ModelSettings("gpt-6.2-sol", "high")


@asynccontextmanager
async def open_lesson(lesson, agent):
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def choose(user, marker, value):
    """Picks `value` in a toggle or select, as a click on that option does."""
    with user:
        (element,) = user.find(marker=marker).elements
        element.value = value


async def should_have(user, marker, **attributes):
    """Waits until the element marked `marker` has `attributes`, as should_see waits for text.

    Async event handlers run in the background, so an element changes a moment after the click.
    """
    for _ in range(20):
        with user:
            (element,) = user.find(marker=marker).elements
            actual = {name: getattr(element, name) for name in attributes}
        if actual == attributes:
            return
        await asyncio.sleep(0.05)
    assert actual == attributes


async def send(user, text, reply):
    user.find(marker="message").type(text)
    user.find(marker="send").click()
    await user.should_see(reply)


async def test_the_lesson_screen_starts_on_rapido_and_turns_use_it(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    async with open_lesson(tmp_path, agent) as user:
        await should_have(user, "preset", value="Rápido")

        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [QUICK]


async def test_caprichado_reaches_the_agent_on_the_next_turn(tmp_path):
    agent = ScriptedAgent([[AssistantText("Primeira.")], [AssistantText("Segunda.")]])
    async with open_lesson(tmp_path, agent) as user:
        await send(user, "oi", "Primeira.")
        choose(user, "preset", "Caprichado")
        await send(user, "de novo", "Segunda.")

    assert agent.turn_settings == [QUICK, CAREFUL]


async def open_settings(user):
    user.find(marker="open-settings").click()
    await user.should_see("Avançado")


async def test_avancado_offers_the_agent_models_and_its_choice_reaches_the_next_turn(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    async with open_lesson(tmp_path, agent) as user:
        await open_settings(user)
        await should_have(user, "model", options={"gpt-6.2-sol": "GPT-6.2-Sol", "gpt-6-luna": "GPT-6-Luna"})
        choose(user, "model", "gpt-6-luna")
        await should_have(user, "effort", options={"low": "Baixo", "medium": "Médio", "high": "Alto"})
        choose(user, "effort", "high")
        user.find("Fechar").click()

        await should_have(user, "preset", value=None)
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [ModelSettings("gpt-6-luna", "high")]


async def test_a_model_without_the_current_effort_falls_back_to_its_default(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    await agent.set_model_settings(ModelSettings("gpt-6.2-sol", "xhigh"))
    async with open_lesson(tmp_path, agent) as user:
        await open_settings(user)
        choose(user, "model", "gpt-6-luna")
        await should_have(user, "effort", value="medium")
        user.find("Fechar").click()
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [ModelSettings("gpt-6-luna", "medium")]


async def test_avancado_matching_a_preset_moves_the_switch_to_it(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    async with open_lesson(tmp_path, agent) as user:
        await open_settings(user)
        choose(user, "effort", "high")
        await should_have(user, "preset", value="Caprichado")
        user.find("Fechar").click()
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [CAREFUL]


async def test_settings_show_the_chatgpt_account_its_plan_and_the_switchs_model(tmp_path):
    async with open_lesson(tmp_path, ScriptedAgent([])) as user:
        await open_settings(user)

        await user.should_see("Conectado com o ChatGPT (plano Plus): professora@example.com")
        await user.should_see("Rápido e Caprichado usam o GPT-6.2-Sol.")


async def test_a_free_account_runs_the_switch_on_gpt_6_luna(tmp_path):
    agent = ScriptedAgent([[AssistantText("Primeira.")], [AssistantText("Segunda.")]], plan="free")
    async with open_lesson(tmp_path, agent) as user:
        await should_have(user, "preset", value="Rápido")
        await send(user, "oi", "Primeira.")
        choose(user, "preset", "Caprichado")
        await send(user, "de novo", "Segunda.")
        await open_settings(user)

        await user.should_see("Conectado com o ChatGPT (plano Free): professora@example.com")
        await user.should_see("Rápido e Caprichado usam o GPT-6-Luna.")

    assert agent.turn_settings == [ModelSettings("gpt-6-luna", "low"), ModelSettings("gpt-6-luna", "high")]


async def test_settings_show_an_api_key_sign_in(tmp_path):
    agent = ScriptedAgent([], logged_in=False)
    async with open_lesson(tmp_path, agent) as user:
        user.find(marker="api-key").type("sk-teste")
        user.find("Usar chave de API").click()
        await user.should_see(marker="open-settings")
        await open_settings(user)

        await user.should_see("Conectado com uma chave de API da OpenAI")
        await user.should_not_see("ChatGPT")


async def test_signing_out_clears_the_credentials_and_goes_back_to_sign_in(tmp_path):
    agent = ScriptedAgent([[AssistantText("Voltei.")]])
    async with open_lesson(tmp_path, agent) as user:
        await open_settings(user)
        user.find("Sair").click()

        await user.should_see("Entrar com o ChatGPT")
        await user.should_not_see(marker="message")
        await user.should_not_see(marker="preset")
        await user.should_not_see(marker="open-settings")
        assert not (await agent.account()).logged_in

        user.find("Entrar com o ChatGPT").click()
        await user.should_see(marker="message")
        await send(user, "oi", "Voltei.")


async def test_settings_show_how_much_of_the_chatgpt_plan_was_used(tmp_path):
    async with open_lesson(tmp_path, ScriptedAgent([])) as user:
        await open_settings(user)

        await user.should_see("Uso do plano do ChatGPT")
        await user.should_see("Limite de 5 horas: 5% usado")
        await user.should_see("Limite semanal: 80% usado")
        await user.should_see("renova")


async def test_the_quota_is_hidden_with_an_api_key(tmp_path):
    agent = ScriptedAgent([], logged_in=False)
    async with open_lesson(tmp_path, agent) as user:
        user.find(marker="api-key").type("sk-teste")
        user.find("Usar chave de API").click()
        await user.should_see(marker="open-settings")
        await open_settings(user)

        await user.should_not_see("Uso do plano")
        await user.should_not_see("usado")


async def test_a_switch_open_across_a_change_of_account_uses_the_new_accounts_model(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]], logged_in=False, plan="free")
    await agent.login(api_key="sk-teste")
    async with open_lesson(tmp_path, agent) as user:
        await should_have(user, "preset", value="Rápido")
        # Another tab signs out and back in with a ChatGPT Free account.
        await agent.logout()
        await agent.login()
        choose(user, "preset", "Caprichado")
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [ModelSettings("gpt-6-luna", "high")]


async def test_avancado_keeps_its_pick_in_a_tab_open_across_a_change_of_account(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]], logged_in=False, plan="free")
    await agent.login(api_key="sk-teste")
    async with open_lesson(tmp_path, agent) as user:
        await should_have(user, "preset", value="Rápido")
        # Another tab signs out and back in with a ChatGPT Free account, whose switch runs on Luna.
        await agent.logout()
        await agent.login()
        await open_settings(user)
        # The pick is what the old account's Caprichado was.
        choose(user, "model", "gpt-6.2-sol")
        choose(user, "effort", "high")
        # Neither of the new account's positions; the old account's Caprichado would apply Luna.
        await should_have(user, "preset", value=None)
        user.find("Fechar").click()
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [ModelSettings("gpt-6.2-sol", "high")]


def slow_presets(agent, seconds=0.5):
    """Makes reading the account's presets take a while, as a catalog fetched over the network does."""
    presets = agent.presets

    async def slow():
        await asyncio.sleep(seconds)
        return await presets()

    agent.presets = slow


async def test_the_switch_applies_at_once_while_codex_is_slow(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    async with open_lesson(tmp_path, agent) as user:
        slow_presets(agent)
        choose(user, "preset", "Caprichado")
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [CAREFUL]


async def test_the_last_pick_in_avancado_wins_while_codex_is_slow(tmp_path):
    agent = ScriptedAgent([[AssistantText("Feito.")]])
    async with open_lesson(tmp_path, agent) as user:
        await open_settings(user)
        slow_presets(agent)
        choose(user, "effort", "high")
        await asyncio.sleep(0.1)
        choose(user, "effort", "xhigh")
        # Long enough for every slow read the two picks started to end.
        await asyncio.sleep(1.5)
        user.find("Fechar").click()
        await send(user, "oi", "Feito.")

    assert agent.turn_settings == [ModelSettings("gpt-6.2-sol", "xhigh")]
