"""Confere a física da aula. Rode na pasta da aula: python -m pytest test_fisica.py

Os valores esperados são escritos à mão, e não recalculados com as fórmulas de fisica.py.
"""

import pytest

from fisica import equacoes

ESPERADO: dict[str, float] = {}


def test_valores_das_equacoes():
    valores = {equacao.nome: equacao.valor for equacao in equacoes()}
    assert valores == pytest.approx(ESPERADO)
