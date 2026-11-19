from contextlib import asynccontextmanager

from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AssistantText
from manimflow.app import lesson_page
from manimflow.fake_agent import ScriptedAgent


@asynccontextmanager
async def open_signed_out(lesson, login_failure=None):
    agent = ScriptedAgent([[AssistantText("Oi, professora.")]], logged_in=False, login_failure=login_failure)
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


async def test_a_signed_out_teacher_sees_both_ways_to_sign_in_and_no_chat(tmp_path):
    async with open_signed_out(tmp_path) as user:
        await user.should_see("Entrar com o ChatGPT")
        await user.should_see(marker="api-key")
        await user.should_see("Usar chave de API")
        await user.should_not_see(marker="message")


async def test_signing_in_with_chatgpt_opens_the_chat(tmp_path):
    async with open_signed_out(tmp_path) as user:
        user.find("Entrar com o ChatGPT").click()

        await user.should_see(marker="message")
        await user.should_not_see("Entrar com o ChatGPT")
        user.find(marker="message").type("oi")
        user.find(marker="send").click()
        await user.should_see("Oi, professora.")


async def test_signing_in_with_an_api_key_opens_the_chat(tmp_path):
    async with open_signed_out(tmp_path) as user:
        user.find(marker="api-key").type("sk-teste")
        user.find("Usar chave de API").click()

        await user.should_see(marker="message")
        await user.should_not_see("Usar chave de API")


async def test_a_failed_sign_in_is_explained_in_portuguese(tmp_path):
    failure = "O login com o ChatGPT não foi concluído. Tente de novo."
    async with open_signed_out(tmp_path, login_failure=failure) as user:
        user.find("Entrar com o ChatGPT").click()

        await user.should_see(failure)
        await user.should_see("Entrar com o ChatGPT")
        await user.should_not_see(marker="message")


async def test_a_signed_in_teacher_goes_straight_to_the_chat(tmp_path):
    agent = ScriptedAgent([])
    async with user_simulation(root=lesson_page(agent, tmp_path)) as user:
        await user.open("/")
        await user.should_see(marker="message")
        await user.should_not_see("Entrar com o ChatGPT")
