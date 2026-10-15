"""Física da aula: relatividade restrita com uma dimensão espacial.

c = 1, tempo em minutos, distância em minutos-luz.
Referenciais:
    S  = Terra  -> coordenadas (x_T, t_T)
    S' = Herói  -> coordenadas (x_H, t_H)
O herói passa pela origem em t_T = t_H = 0 e anda no sentido +x a V = 0,6c.
A Terra, onde está o espelho, fica parada em x_T = DIST = 8.

Os eventos estão em coordenadas da Terra. As coordenadas do herói saem de lorentz().
Este arquivo é a única fonte dos números: cenas.py só desenha o que sai daqui, e
equacoes() é o gabarito que o painel de equações mostra e test_fisica.py confere.
"""

from math import sqrt
from typing import NamedTuple

V = 0.6  # velocidade do herói
DIST = 8  # distância inicial até a Terra, medida na Terra (min-luz)


def gamma(v):
    return 1 / sqrt(1 - v**2)


GAMMA = gamma(V)


def lorentz(x, t, v=V):
    """(x_T, t_T) -> (x_H, t_H): x' = γ(x − vt), t' = γ(t − vx)."""
    g = gamma(v)
    return g * (x - v * t), g * (t - v * x)


def lorentz_inv(xh, th, v=V):
    """(x_H, t_H) -> (x_T, t_T): x = γ(x' + vt'), t = γ(t' + vx')."""
    g = gamma(v)
    return g * (xh + v * th), g * (th + v * xh)


def velocidade_relativa(w, u):
    """Velocidade de quem anda a w na Terra, vista por um referencial que anda a u.

    É a composição relativística: (w − u)/(1 − uw), que nunca passa de c.
    """
    return (w - u) / (1 - u * w)


def intervalo(a, b):
    """Intervalo invariante c²Δt² − Δx² entre dois eventos (x, t)."""
    return (b[1] - a[1]) ** 2 - (b[0] - a[0]) ** 2


# Eventos, em coordenadas da Terra (x_T, t_T). Estão escritos à mão para o desenho
# ficar exato, e test_fisica.py confere que batem com a física.
EMISSAO = (0, 0)  # o herói emite a luz na origem
REFLEXAO = (8, 8)  # a luz chega ao espelho, em x_T = 8
COLISAO = (6, 10)  # a luz refletida reencontra o herói
EVENTOS = {"Emissão": EMISSAO, "Reflexão": REFLEXAO, "Colisão": COLISAO}

# Onde o herói está, para a Terra, no instante da Reflexão: (4,8; 8).
# A linha de mundo dele é desenhada em dois trechos, antes e depois desse ponto.
HEROI_NA_REFLEXAO = (V * DIST, DIST)

# Resultados das análises que aparecem nas figuras
CONTRACAO = DIST / GAMMA  # 6,4: distância até a Terra para o herói, em t_H = 0
SIMULTANEIDADE = V * DIST  # 4,8: relógio da Terra no instante da Emissão, para o herói
IDA_VOLTA = lorentz(*COLISAO)[1]  # 8: tempo próprio do herói da Emissão à Colisão
TEMPO_PROPRIO = sqrt(intervalo(EMISSAO, COLISAO))  # 8: τ da hipérbole c²t² − x² = τ²
CHEGADA = CONTRACAO / V  # ≈ 10,67: t_H em que a Terra chega ao herói


# --- Ecos (referencial do herói) ----------------------------------------------


def eco(x):
    """Δt_H da ida e volta da luz, com o espelho em x_H no instante da emissão.

    A luz e o espelho se aproximam a 1 + v e a volta leva o mesmo tempo que a ida,
    então Δt = 2x/(1 + v). O fator 2/(1 + v) dá 1,25 e coincide com γ só porque v = 0,6.
    """
    return 2 * x / (1 + V)


def lista_ecos(n):
    """O herói reemite a luz a cada retorno: [(t_H da emissão, x_H do espelho, Δt_H), ...].

    A cada eco, o tempo que falta até a chegada cai pelo fator (1 − v)/(1 + v), que aqui é 1/4.
    """
    t, lista = 0.0, []
    for _ in range(n):
        x = CONTRACAO - V * t
        dt = eco(x)
        lista.append((t, x, dt))
        t += dt
    return lista


# --- Equações da aula ------------------------------------------------------------


class Equacao(NamedTuple):
    nome: str
    latex: str
    valor: float
    unidade: str


def equacoes():
    """Todas as contas da aula, na ordem da apresentação, com o valor calculado aqui.

    É o gabarito dos números dos slides. Cada valor sai da fórmula, não dos eventos
    escritos à mão, para que test_fisica.py possa conferir uma coisa com a outra.
    """
    t_colisao = 2 * DIST / (1 + V)  # a luz refletida (x = 2d − t) encontra o herói (x = vt)
    x_colisao = V * t_colisao
    xh_reflexao, th_reflexao = lorentz(DIST, DIST)
    xh_colisao, th_colisao = lorentz(x_colisao, t_colisao)
    return [
        Equacao("Velocidade do herói", r"v", V, "c"),
        Equacao("Distância até a Terra, medida na Terra", r"d", DIST, "min-luz"),
        Equacao("Fator de Lorentz", r"\gamma = \frac{1}{\sqrt{1 - v^2}}", GAMMA, ""),
        # 1. Coordenadas dos eventos na Terra
        Equacao("Reflexão na Terra: posição", r"x_T = d", DIST, "min-luz"),
        Equacao("Reflexão na Terra: instante", r"t_T = d / c", DIST, "min"),
        Equacao("Colisão na Terra: instante", r"t_T = \frac{2d}{1 + v}", t_colisao, "min"),
        Equacao("Colisão na Terra: posição", r"x_T = v\,t_T", x_colisao, "min-luz"),
        # 1. Transformações de Lorentz, nos dois sentidos
        Equacao("Reflexão no herói: posição", r"x_H = \gamma\,(x_T - v\,t_T)", xh_reflexao, "min-luz"),
        Equacao("Reflexão no herói: instante", r"t_H = \gamma\,(t_T - v\,x_T)", th_reflexao, "min"),
        Equacao("Colisão no herói: posição", r"x_H = \gamma\,(x_T - v\,t_T)", xh_colisao, "min-luz"),
        Equacao("Colisão no herói: instante", r"t_H = \gamma\,(t_T - v\,x_T)", th_colisao, "min"),
        Equacao(
            "Reflexão de volta na Terra: posição",
            r"x_T = \gamma\,(x_H + v\,t_H)",
            lorentz_inv(xh_reflexao, th_reflexao)[0],
            "min-luz",
        ),
        Equacao(
            "Reflexão de volta na Terra: instante",
            r"t_T = \gamma\,(t_H + v\,x_H)",
            lorentz_inv(xh_reflexao, th_reflexao)[1],
            "min",
        ),
        # 2. Intervalo invariante
        Equacao(
            "Intervalo Emissão → Reflexão (tipo luz)",
            r"s^2 = c^2\Delta t^2 - \Delta x^2",
            intervalo((0, 0), (DIST, DIST)),
            "min²",
        ),
        Equacao(
            "Intervalo Reflexão → Colisão (tipo luz)",
            r"s^2 = c^2\Delta t^2 - \Delta x^2",
            intervalo((DIST, DIST), (x_colisao, t_colisao)),
            "min²",
        ),
        Equacao(
            "Intervalo Emissão → Colisão (tipo tempo)",
            r"s^2 = c^2\Delta t^2 - \Delta x^2",
            intervalo((0, 0), (x_colisao, t_colisao)),
            "min²",
        ),
        Equacao("Tempo próprio do herói", r"\tau = \sqrt{s^2}", sqrt(intervalo((0, 0), (x_colisao, t_colisao))), "min"),
        # 3. Dilatação do tempo, da Emissão à Colisão
        Equacao("Dilatação do tempo", r"\Delta t_T = \gamma\,\Delta t_H", GAMMA * th_colisao, "min"),
        # 4. Contração do espaço
        Equacao("Distância até a Terra para o herói", r"L = \frac{L_0}{\gamma}", DIST / GAMMA, "min-luz"),
        # 5. Relatividade da simultaneidade
        Equacao(
            "Relógio da Terra simultâneo à Emissão, para o herói",
            r"t_T = v\,x_T",
            V * DIST,
            "min",
        ),
        # 6. Radar
        Equacao("Radar: instante da Reflexão para o herói", r"t_H = \frac{\Delta t_H}{2}", th_colisao / 2, "min"),
        # 7. Ecos
        Equacao("Primeiro eco: ida e volta", r"\Delta t_H = \frac{2\,x_H}{1 + v}", eco(DIST / GAMMA), "min"),
        Equacao("Razão entre ecos seguidos", r"\frac{1 - v}{1 + v}", (1 - V) / (1 + V), ""),
        Equacao("Chegada da Terra ao herói", r"t_H = \frac{L}{v}", DIST / GAMMA / V, "min"),
    ]
