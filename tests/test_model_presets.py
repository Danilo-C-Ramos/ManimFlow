"""Which model the "Rápido / Caprichado" switch runs on, given the plan and the account's catalog."""

import pytest

from manimflow.agent import ModelOption, ModelSettings
from manimflow.model_presets import CAREFUL, QUICK, choose_model, preset_name, presets

ALL = ("low", "medium", "high", "xhigh", "max")


def option(model, efforts=ALL, default_effort="low", default=False):
    return ModelOption(model, model.upper(), efforts, default_effort, default)


# The catalog a ChatGPT Plus account got on 2026-11-25, shortened.
PLUS = [option("gpt-6.2-sol", default=True), option("gpt-6.2-astra"), option("gpt-6.1-sol"), option("gpt-6-luna")]


@pytest.mark.parametrize("plan", ["plus", "pro", "prolite", "business", "enterprise", "edu", "unknown", None])
def test_paid_plans_and_api_keys_get_gpt_6_2_sol(plan):
    assert choose_model(plan, PLUS).model == "gpt-6.2-sol"


@pytest.mark.parametrize("plan", ["free", "go"])
def test_free_and_go_get_gpt_6_luna_even_from_a_catalog_that_lists_more(plan):
    assert choose_model(plan, PLUS).model == "gpt-6-luna"


def test_a_catalog_without_gpt_6_2_falls_back_to_gpt_6_1_sol():
    # Such as an Enterprise workspace whose administrator hasn't turned GPT-6.2 on.
    catalog = [option("gpt-6.1-terra", default=True), option("gpt-6.1-sol")]

    assert choose_model("enterprise", catalog).model == "gpt-6.1-sol"


def test_a_catalog_with_none_of_the_plans_models_gets_its_own_default():
    catalog = [option("gpt-7-nova"), option("gpt-7-luna", default=True)]

    assert choose_model("free", catalog).model == "gpt-7-luna"
    assert choose_model("plus", catalog).model == "gpt-7-luna"
    assert choose_model("plus", catalog[:1]).model == "gpt-7-nova"


def test_without_a_catalog_the_plans_first_model_runs_at_the_switchs_efforts():
    assert presets(choose_model("plus", [])) == {
        QUICK: ModelSettings("gpt-6.2-sol", "low"),
        CAREFUL: ModelSettings("gpt-6.2-sol", "high"),
    }
    assert presets(choose_model("free", []))[QUICK] == ModelSettings("gpt-6-luna", "low")


def test_an_effort_the_model_lacks_becomes_its_default():
    assert presets(option("gpt-6-luna", efforts=("medium", "xhigh"), default_effort="medium")) == {
        QUICK: ModelSettings("gpt-6-luna", "medium"),
        CAREFUL: ModelSettings("gpt-6-luna", "medium"),
    }


def test_the_switch_position_follows_the_accounts_presets():
    luna = presets(option("gpt-6-luna"))

    assert preset_name(luna, ModelSettings("gpt-6-luna", "high")) == CAREFUL
    assert preset_name(luna, ModelSettings("gpt-6.2-sol", "high")) is None
