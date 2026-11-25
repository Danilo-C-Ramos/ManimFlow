"""`manimflow account`, against the real bundled app-server, offline."""

import asyncio
import json

from manimflow.account_report import NOT_SIGNED_IN
from manimflow.cli import main
from manimflow.codex_agent import CodexAgent, default_codex_home


def account(monkeypatch, tmp_path, capsys, *args):
    """Runs `manimflow account` with ManimFlow's own folder in `tmp_path`; returns its exit code and output."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    code = main(["account", *args])
    return code, capsys.readouterr()


def sign_in_with_an_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    async def sign_in():
        agent = CodexAgent(default_codex_home())
        try:
            await agent.login(api_key="sk-teste")
        finally:
            await agent.close()

    asyncio.run(sign_in())


def test_it_lists_the_models_and_the_switchs_choice_for_an_api_key(monkeypatch, tmp_path, capsys):
    sign_in_with_an_api_key(monkeypatch, tmp_path)

    code, output = account(monkeypatch, tmp_path, capsys)

    assert code == 0, output.err
    lines = output.out.splitlines()
    assert lines[:3] == [
        "Conta: chave de API da OpenAI",
        "Rápido: gpt-6.2-sol, esforço low",
        "Caprichado: gpt-6.2-sol, esforço high",
    ]
    assert any(line.startswith("  * gpt-6.2-sol ") for line in lines)
    assert any(line.startswith("    gpt-6-luna ") for line in lines)
    # An API key has no plan, so no plan usage either.
    assert not [line for line in lines if line.startswith("Uso do plano")]


def test_its_json_report_says_when_manimflow_is_not_signed_in(monkeypatch, tmp_path, capsys):
    code, output = account(monkeypatch, tmp_path, capsys, "--json")

    report = json.loads(output.out)
    assert code == 1
    assert report["ok"] is False
    assert report["command"] == "account"
    assert report["account"] == {"logged_in": False, "method": None, "email": None, "plan": None}
    assert report["errors"] == [NOT_SIGNED_IN]
    assert report["presets"]["Rápido"] == {"model": "gpt-6.2-sol", "effort": "low"}
    assert {"gpt-6.2-sol", "gpt-6-luna"} <= {model["model"] for model in report["models"]}
    assert report["quota"] is None
