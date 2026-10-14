import shutil

import pytest

from conftest import FIXTURES

INVALID_PLANS = FIXTURES / "planos_invalidos"


def test_valid_plan_passes(manimflow, lesson):
    result = manimflow("plan", "validate", str(lesson), "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    report = result.report
    assert report["ok"] is True
    assert report["command"] == "plan validate"
    assert report["errors"] == []


def test_missing_plan_file_is_reported(manimflow, lesson):
    (lesson / "plano.yaml").unlink()

    result = manimflow("plan", "validate", str(lesson), "--json")

    assert result.returncode != 0
    assert result.report["ok"] is False
    assert any("plano.yaml" in error for error in result.report["errors"])


@pytest.mark.parametrize(
    "fixture, expected",
    [
        ("id_duplicado.yaml", 'Há mais de um estado com o id "S0"'),
        ("cena_desconhecida.yaml", 'Estado S1: a cena "T09" não existe em cenas.py'),
        ("nao_vizinhos.yaml", "Transição S0 → S2: S2 não vem logo depois de S0"),
        ("estado_desconhecido.yaml", 'Transição S0 → S9: o estado "S9" não existe no plano'),
        ("sem_titulo.yaml", 'Estado S1: falta o campo "titulo"'),
        ("sem_id.yaml", 'Estado 2: falta o campo "id"'),
        ("sem_duracao.yaml", 'Transição S0 → S1: falta o campo "duracao"'),
        ("sem_estados.yaml", 'Falta a lista "estados"'),
        ("duracao_negativa.yaml", 'Transição S0 → S1: "duracao" precisa ser um número de segundos maior que zero'),
        ("yaml_invalido.yaml", "O plano.yaml não é um YAML válido"),
        ("cena_nome_invalido.yaml", 'Estado S0: "../x" não serve como nome de cena'),
        ("id_invalido.yaml", '"S 1" não serve como id de estado'),
        ("duracao_nan.yaml", 'Transição S0 → S1: "duracao" precisa ser um número de segundos maior que zero'),
        ("vazio.yaml", 'Falta a lista "estados"'),
    ],
)
def test_invalid_plan_is_rejected_with_a_clear_error(manimflow, lesson, fixture, expected):
    shutil.copyfile(INVALID_PLANS / fixture, lesson / "plano.yaml")

    result = manimflow("plan", "validate", str(lesson), "--json")

    assert result.returncode != 0
    report = result.report
    assert report["ok"] is False
    assert any(expected in error for error in report["errors"]), report["errors"]


def test_errors_without_json_go_to_stderr(manimflow, lesson):
    shutil.copyfile(INVALID_PLANS / "nao_vizinhos.yaml", lesson / "plano.yaml")

    result = manimflow("plan", "validate", str(lesson))

    assert result.returncode != 0
    assert "S2 não vem logo depois de S0" in result.stderr
    assert result.stdout == ""


def errors_for(manimflow, lesson) -> list[str]:
    result = manimflow("plan", "validate", str(lesson), "--json")
    assert result.returncode != 0
    return result.report["errors"]


def test_state_with_a_missing_field_is_not_also_reported_as_unknown(manimflow, lesson):
    shutil.copyfile(INVALID_PLANS / "sem_titulo.yaml", lesson / "plano.yaml")

    errors = errors_for(manimflow, lesson)

    assert errors == ['Estado S1: falta o campo "titulo".']


def test_helper_class_is_not_accepted_as_a_scene(manimflow, lesson):
    with open(lesson / "cenas.py", "a", encoding="utf-8") as scenes:
        scenes.write("\n\nclass Janela:\n    largura = 2\n")
    plan = lesson / "plano.yaml"
    plan.write_text(plan.read_text(encoding="utf-8").replace("cena: S0", "cena: Janela"), encoding="utf-8")

    errors = errors_for(manimflow, lesson)

    assert errors == ['Estado S0: a classe "Janela" de cenas.py não é uma cena.']


def test_scene_inheriting_from_a_lesson_base_class_is_accepted(manimflow, lesson):
    with open(lesson / "cenas.py", "a", encoding="utf-8") as scenes:
        scenes.write("\n\nclass Base(Scene):\n    pass\n\n\nclass S0b(Base):\n    pass\n")
    plan = lesson / "plano.yaml"
    plan.write_text(plan.read_text(encoding="utf-8").replace("cena: S0", "cena: S0b"), encoding="utf-8")

    result = manimflow("plan", "validate", str(lesson), "--json")

    assert result.returncode == 0, result.report["errors"]


@pytest.mark.parametrize("name", ["plano.yaml", "cenas.py"])
def test_file_not_in_utf8_is_reported(manimflow, lesson, name):
    # Saved by an editor that uses the Windows code page, with an accent in it.
    path = lesson / name
    path.write_bytes((path.read_text(encoding="utf-8") + "\n# animação\n").encode("cp1252"))

    errors = errors_for(manimflow, lesson)

    assert any(f"O {name} não está em UTF-8" in error for error in errors), errors


def test_missing_lesson_folder_is_reported(manimflow, tmp_path):
    errors = errors_for(manimflow, tmp_path / "nao-existe")

    assert errors == [f"Não encontrei a pasta da aula {tmp_path / 'nao-existe'}."]
