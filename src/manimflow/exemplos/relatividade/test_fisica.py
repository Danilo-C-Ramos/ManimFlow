"""Confere a física da aula. Rode na pasta da aula: python -m pytest test_fisica.py

Os valores esperados são os da tabela de eventos e das análises do CONTEXTO.md,
escritos à mão, e não recalculados com as fórmulas de fisica.py.
"""

from math import isclose

import pytest

from fisica import (
    CHEGADA, COLISAO, CONTRACAO, EMISSAO, EVENTOS, GAMMA, HEROI_NA_REFLEXAO, IDA_VOLTA, REFLEXAO,
    SIMULTANEIDADE, TEMPO_PROPRIO, equacoes, lista_ecos, lorentz, lorentz_inv, velocidade_relativa,
)  # fmt: skip

ESPERADO = {
    "Velocidade do herói": 0.6,
    "Distância até a Terra, medida na Terra": 8,
    "Fator de Lorentz": 1.25,
    "Reflexão na Terra: posição": 8,
    "Reflexão na Terra: instante": 8,
    "Colisão na Terra: instante": 10,
    "Colisão na Terra: posição": 6,
    "Reflexão no herói: posição": 4,
    "Reflexão no herói: instante": 4,
    "Colisão no herói: posição": 0,
    "Colisão no herói: instante": 8,
    "Reflexão de volta na Terra: posição": 8,
    "Reflexão de volta na Terra: instante": 8,
    "Intervalo Emissão → Reflexão (tipo luz)": 0,
    "Intervalo Reflexão → Colisão (tipo luz)": 0,
    "Intervalo Emissão → Colisão (tipo tempo)": 64,
    "Tempo próprio do herói": 8,
    "Dilatação do tempo": 10,
    "Distância até a Terra para o herói": 6.4,
    "Relógio da Terra simultâneo à Emissão, para o herói": 4.8,
    "Radar: instante da Reflexão para o herói": 4,
    "Primeiro eco: ida e volta": 8,
    "Razão entre ecos seguidos": 0.25,
    "Chegada da Terra ao herói": 32 / 3,
}


def valores():
    return {eq.nome: eq.valor for eq in equacoes()}


@pytest.mark.parametrize("nome, esperado", ESPERADO.items())
def test_valor_da_equacao(nome, esperado):
    assert valores()[nome] == pytest.approx(esperado, abs=1e-9)


def test_toda_equacao_tem_valor_conferido():
    assert sorted(valores()) == sorted(ESPERADO)


def test_equacoes_tem_nome_latex_valor_e_unidade():
    for eq in equacoes():
        nome, latex, valor, unidade = eq
        assert nome and latex
        assert isinstance(valor, (int, float))
        assert isinstance(unidade, str)


def test_eventos_escritos_a_mao_batem_com_a_fisica():
    assert EMISSAO == (0, 0)
    # Reflexão: a luz sai da origem (x = t) e chega ao espelho em x = 8.
    assert REFLEXAO == (8, 8)
    # Colisão: a luz refletida (x = 16 − t) encontra o herói (x = 0,6·t).
    x, t = COLISAO
    assert isclose(x, 0.6 * t) and isclose(x, 16 - t)


def test_coordenadas_do_heroi_nos_eventos():
    esperado = {"Emissão": (0, 0), "Reflexão": (4, 4), "Colisão": (0, 8)}
    for nome, (x, t) in EVENTOS.items():
        assert lorentz(x, t) == pytest.approx(esperado[nome])
        assert lorentz_inv(*lorentz(x, t)) == pytest.approx((x, t))


def test_resultados_usados_nas_figuras():
    assert GAMMA == pytest.approx(1.25)
    assert CONTRACAO == pytest.approx(6.4)
    assert SIMULTANEIDADE == pytest.approx(4.8)
    assert IDA_VOLTA == pytest.approx(8)
    assert TEMPO_PROPRIO == pytest.approx(8)
    assert CHEGADA == pytest.approx(32 / 3)
    assert HEROI_NA_REFLEXAO == pytest.approx((4.8, 8))


def test_ecos_caem_a_um_quarto():
    assert [dt for _, _, dt in lista_ecos(4)] == pytest.approx([8, 2, 0.5, 0.125])
    assert [t for t, _, _ in lista_ecos(4)] == pytest.approx([0, 8, 10, 10.5])


def test_velocidade_relativa():
    assert velocidade_relativa(0.6, 0) == pytest.approx(0.6)  # vista da Terra
    assert velocidade_relativa(0.6, 0.6) == pytest.approx(0)  # o herói visto por ele mesmo
    assert velocidade_relativa(0, 0.6) == pytest.approx(-0.6)  # a Terra vista pelo herói
    assert velocidade_relativa(0.6, -0.6) == pytest.approx(1.2 / 1.36)  # nunca passa de c
