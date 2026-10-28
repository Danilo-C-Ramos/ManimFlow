"""A física da aula. Só contas: o desenho fica em cenas.py, que tira daqui todos os números."""

from typing import NamedTuple


class Equacao(NamedTuple):
    nome: str
    latex: str
    valor: float
    unidade: str


def equacoes():
    """Todas as contas da aula, na ordem da apresentação, com o valor calculado aqui.

    O painel de equações do ManimFlow mostra esta lista, e test_fisica.py confere os valores.
    """
    return []
