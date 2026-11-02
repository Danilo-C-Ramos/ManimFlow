"""Signing in to Codex through the adapter, against the real bundled app-server, offline."""

import urllib.parse
import urllib.request

import pytest

from manimflow.agent import Account, LoginFailed
from manimflow.codex_agent import CodexAgent


def deny_access(auth_url):
    """Plays the browser: the teacher refuses access, and OpenAI redirects to the loopback."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    callback = query["redirect_uri"][0] + "?" + urllib.parse.urlencode(
        {"error": "access_denied", "error_description": "denied", "state": query["state"][0]}
    )
    urllib.request.urlopen(callback, timeout=10).read()


async def test_an_api_key_login_survives_a_restart(tmp_path):
    home = tmp_path / "codex"
    agent = CodexAgent(home)
    try:
        assert await agent.account() == Account(logged_in=False)
        assert await agent.login(api_key=" sk-teste \n") == Account(logged_in=True, method="api_key")
    finally:
        await agent.close()

    restarted = CodexAgent(home)
    try:
        assert await restarted.account() == Account(logged_in=True, method="api_key")
    finally:
        await restarted.close()


async def test_an_empty_api_key_is_refused_in_portuguese(tmp_path):
    agent = CodexAgent(tmp_path / "codex")
    try:
        with pytest.raises(LoginFailed, match="^Cole a sua chave de API da OpenAI para entrar.$"):
            await agent.login(api_key="   ")
        assert await agent.account() == Account(logged_in=False)
    finally:
        await agent.close()


async def test_chatgpt_login_opens_the_browser_on_a_loopback_redirect(tmp_path):
    opened = []

    def browser(url):
        opened.append(url)
        deny_access(url)

    agent = CodexAgent(tmp_path / "codex", open_browser=browser)
    try:
        with pytest.raises(LoginFailed, match="^O login com o ChatGPT não foi concluído. Tente de novo.$"):
            await agent.login()
        assert await agent.account() == Account(logged_in=False)
    finally:
        await agent.close()

    (url,) = opened
    redirect = urllib.parse.urlparse(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["redirect_uri"][0])
    assert redirect.hostname == "127.0.0.1"


async def test_logout_deletes_the_stored_credentials(tmp_path):
    home = tmp_path / "codex"
    agent = CodexAgent(home)
    try:
        await agent.login(api_key="sk-teste")
        await agent.logout()
        assert await agent.account() == Account(logged_in=False)
    finally:
        await agent.close()

    restarted = CodexAgent(home)
    try:
        assert await restarted.account() == Account(logged_in=False)
    finally:
        await restarted.close()


async def test_an_api_key_has_no_plan_quota(tmp_path):
    agent = CodexAgent(tmp_path / "codex")
    try:
        assert await agent.quota() is None
        await agent.login(api_key="sk-teste")
        assert await agent.quota() is None
    finally:
        await agent.close()
