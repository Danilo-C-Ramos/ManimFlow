"""Cenas da aula, na ordem da apresentação. Só desenho: todo número vem de fisica.py.

    C_Contexto           estático: eixo x em 1D com as posições em t = 0 nos dois referenciais
    S0_Base              eixos da Terra, linha de mundo da Terra, herói na origem
    S1_EixosHeroi        S0 -> S1   eixos do herói se fecham de 0 até v
    S2_Reflexao          S1 -> S2   herói e raio até a Reflexão, com as coordenadas da Terra
    S2b_InstanteReflexao S2 -> S2b  em verde, tracejado t_T = 8 da Reflexão até o herói (6,4) e dali vertical até x_T = 4,8
    S2c_CoordsHeroi      S2b -> S2c o verde some e entram projeções e coordenadas do herói na Reflexão
    S3_Colisao           S2c -> S3  raio refletido até a Colisão e as coordenadas dela nos dois referenciais
    S5_Simultaneidade    S3 -> S5   linha de simultaneidade gira até t_H = 0
    R_RefHeroi           S3 -> R    boost até o referencial do herói e tracejados verdes da Reflexão
    D_Dilatacao          estático: hipérbole do intervalo invariante

    Ecos, no referencial do herói, que reemite a luz a cada retorno:
    G_TempoEco           estático: Δt_H da ida e volta pela distância da Terra na emissão
    G_TempoEcoT          estático: o mesmo gráfico com o instante t_H da emissão no eixo x, para comparar
    E0_Ecos              estático: eixos do herói, Terra se aproximando, herói na origem
    E_Ecos               E0 -> E    luz em zigue-zague até a Terra chegar, com cotas de 8, 2 e 0,5 min
    R_Ecos               R -> E     somem os eixos da Terra, o verde e os textos dos eventos, e os ecos seguem da Colisão

Como ler este arquivo
---------------------
O arquivo tem três partes, nesta ordem:

    Estilo     cores, fontes, a região desenhada (Janela) e peças pequenas como num() e linha_heroi()
    Diagrama   Diagrama monta eixos, linhas de mundo e eventos; Estados tem as listas S0 a S3;
               Boost redesenha tudo num referencial que anda; Ecos desenha o zigue-zague da luz
    Cenas      só as classes Scene, que posicionam e animam o que sai do Diagrama

Cada classe de cena é uma cena, e o Manim chama o `construct()` dela. `self.add(...)` põe
mobjects na tela sem animação, `self.play(...)` anima, e `self.wait(...)` segura o
quadro.

O slide alterna imagens estáticas e transições curtas. Um estado estático é uma
lista de mobjects, como `E.s2()`, e a ordem da lista é a ordem das camadas: o
primeiro fica no fundo. Cada transição começa com `self.add(*E.sN())` e termina
com a tela igual a `E.sN+1()`. O PNG de um estado é o último quadro da cena, então
a imagem e o vídeo nunca divergem.

Quando uma forma muda continuamente, a cena usa um `ValueTracker` (um número
animável) e `always_redraw(f)`, que chama `f` a cada quadro e redesenha tudo com o
valor atual. No fim, o objeto redesenhado sai e entra o estado estático equivalente.

Prévia rápida:  manimflow preview <pasta da aula> S1_EixosHeroi
Renderização:   manimflow render <pasta da aula> S1_EixosHeroi
"""

from dataclasses import dataclass, fields
from functools import cached_property
from math import asinh, atanh, cosh, sinh
from types import SimpleNamespace

import numpy as np
from manim import *

from fisica import (
    CHEGADA, COLISAO, CONTRACAO, DIST, EVENTOS, HEROI_NA_REFLEXAO, IDA_VOLTA, REFLEXAO, SIMULTANEIDADE,
    TEMPO_PROPRIO, V,
    eco, gamma, lista_ecos, lorentz, lorentz_inv, velocidade_relativa,
)  # fmt: skip


# #############################################################################
# Estilo: visual comum a todas as cenas. Ajusta o Manim para fundo branco e texto escuro.
# #############################################################################

# Fundo branco, como o slide.
config.background_color = "#FFFFFF"

COR_TEXTO = "#1A1A1A"
COR_TERRA = "#1F6FB2"
COR_HEROI = "#D9480F"
COR_LUZ = "#B8860B"
COR_EVENTO = COR_TEXTO
COR_DESTAQUE = "#2B8A3E"
COR_HEROI_ESCURO = "#9A3412"
LARG_HEROI = 7
CONTORNO_HEROI = 2

# O Manim desenha em branco por padrão, e branco some no fundo do slide.
for _cls in (Tex, MathTex, Text, Dot, Line, DashedLine, Arrow):
    _cls.set_default(color=COR_TEXTO)

FS_ROTULO = 30
FS_COORD = 26
FS_NUM = 22

MARGEM_DIR = 0.95
MARGEM_TOPO = 0.3


def lerp(a, b, s):
    return a + (b - a) * s


@dataclass(frozen=True)
class Janela:
    """Região do diagrama, em min-luz, e a escala na tela.

    O retângulo da janela, mais as margens dos rótulos dos eixos, fica centrado no
    quadro. A imagem é pensada como tela cheia, e o slide decide o tamanho.
    """

    x_min: float
    x_max: float
    t_min: float
    t_max: float
    u: float  # unidades de tela por min-luz

    @property
    def canto(self):
        """Posição na tela de (x_min, t_min)."""
        largura = (self.x_max - self.x_min) * self.u + MARGEM_DIR
        altura = (self.t_max - self.t_min) * self.u + MARGEM_TOPO
        return np.array([-largura / 2, -altura / 2, 0])

    def p(self, x, t):
        """Ponto (x, t) do espaço-tempo -> posição na tela."""
        return self.canto + self.u * np.array([x - self.x_min, t - self.t_min, 0])

    def limites(self):
        return [(self.x_min, self.x_max), (self.t_min, self.t_max)]

    def interpola(self, outra, s):
        return Janela(*(lerp(getattr(self, f.name), getattr(outra, f.name), s) for f in fields(self)))


# Janelas do diagrama da Terra (S0 a S5, D) e do herói, no fim do R_RefHeroi. A do
# herói vai mais para a esquerda e para baixo, onde ficam os eixos da Terra.
JANELA_T = Janela(-2.2, 10.5, -1.2, 11.5, 0.58)
JANELA_H = Janela(-4.5, 10.5, -2.5, 11.5, 0.525)
# Ecos: mais alta que larga, porque o herói fica parado em x_H = 0 e a Terra vem de 6,4.
# À esquerda do eixo ct_H ficam os números e as cotas dos Δt.
JANELA_E = Janela(-3.4, 8.0, -1.0, 12.0, 0.56)


def fmt(n, casas=2):
    """Número com vírgula decimal e sem zeros inúteis: 4.80 -> '4,8', 8.0 -> '8'."""
    s = f"{n:.{casas}f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s.replace(".", ",")


def num(n):
    """Número formatado para MathTex com vírgula decimal."""
    return fmt(n).replace(",", "{,}")


def par(x, t):
    return rf"({num(x)},\ {num(t)})"


def linha_heroi(a, b):
    """Contorno branco e linha. Anime com Create(..., lag_ratio=0). No padrão, o Manim
    desenha o contorno inteiro antes, e ele apaga o eixo ct_H à frente do herói."""
    linha = Line(a, b, color=COR_HEROI_ESCURO, stroke_width=LARG_HEROI)
    return VGroup(Line(a, b, color="#FFFFFF", stroke_width=LARG_HEROI + 2 * CONTORNO_HEROI), linha)


def rotulo_eixo(simbolo, cor):
    return VGroup(
        MathTex(simbolo, color=cor, font_size=34),
        Tex("(min-luz)", color=cor, font_size=20),
    ).arrange(DOWN, buff=0.06)


# #############################################################################
# Diagrama: as peças dos diagramas de Minkowski, prontas para as cenas
# #############################################################################

def clip_raio(d, jan):
    """Maior s >= 0 tal que s·d (a partir da origem) fica dentro da janela."""
    s = np.inf
    for i, (lo, hi) in enumerate(jan.limites()):
        if d[i] > 1e-12:
            s = min(s, hi / d[i])
        elif d[i] < -1e-12:
            s = min(s, lo / d[i])
    return s


def clip_reta(p, d, jan):
    """Segmento da reta p + s·d dentro da janela, ou None."""
    s0, s1 = -np.inf, np.inf
    for i, (lo, hi) in enumerate(jan.limites()):
        if abs(d[i]) < 1e-12:
            if not lo <= p[i] <= hi:
                return None
            continue
        a, b = (lo - p[i]) / d[i], (hi - p[i]) / d[i]
        s0, s1 = max(s0, min(a, b)), min(s1, max(a, b))
    if s0 >= s1:
        return None
    return (p[0] + s0 * d[0], p[1] + s0 * d[1]), (p[0] + s1 * d[0], p[1] + s1 * d[1])


class Diagrama:
    """Constrói os mobjects dos estados. `obs` é o referencial com eixos ortogonais, 'T' ou 'H'.

    Os eventos vêm de fisica.py, em coordenadas da Terra. No diagrama do herói, passam por lorentz().
    """

    def __init__(self, obs="T", jan=JANELA_T):
        self.obs = obs
        self.jan = jan
        self.cor = COR_TERRA if obs == "T" else COR_HEROI

    # Monta os eixos ortogonais só quando alguém usa, porque o boost cria um Diagrama por quadro.
    @cached_property
    def ax(self):
        j, cor, obs = self.jan, self.cor, self.obs
        ax = Axes(
            x_range=[j.x_min, j.x_max, 1],
            y_range=[j.t_min, j.t_max, 1],
            x_length=(j.x_max - j.x_min) * j.u,
            y_length=(j.t_max - j.t_min) * j.u,
            axis_config={
                "color": cor,
                "stroke_width": 2.5,
                "tip_width": 0.18,
                "tip_height": 0.18,
                "tick_size": 0.06,
                "font_size": FS_NUM,
                "decimal_number_config": {"num_decimal_places": 0, "color": cor},
            },
            x_axis_config={"numbers_to_include": [n for n in (2, 4, 6, 8, 10) if n <= j.x_max - 0.4]},
            # no diagrama do herói, o 8 do ct_H cairia em cima da Colisão
            y_axis_config={"numbers_to_include": [n for n in (2, 4, 6, 8, 10) if obs == "T" or n != IDA_VOLTA]},
        )
        ax.shift(j.canto - ax.c2p(j.x_min, j.t_min))
        return ax

    @cached_property
    def rot_x(self):
        return rotulo_eixo(f"x_{self.obs}", self.cor).next_to(self.p(self.jan.x_max, 0), RIGHT, buff=0.15)

    @cached_property
    def rot_t(self):
        return rotulo_eixo(f"ct_{self.obs}", self.cor).next_to(self.p(0, self.jan.t_max), RIGHT, buff=0.2)

    def p(self, x, t):
        return self.jan.p(x, t)

    # --- Elementos fixos ----------------------------------------------------

    def eixos(self):
        return VGroup(self.ax, self.rot_x, self.rot_t)

    def linha_terra(self):
        """Linha de mundo da Terra (espelho)."""
        if self.obs == "T":
            a, b = (DIST, 0), (DIST, self.jan.t_max)
            rot_pos, rot_dir = (DIST, self.jan.t_max - 0.6), RIGHT
        else:
            # No referencial do herói a Terra se aproxima com velocidade −v.
            # Começa em t_H = 0, a 6,4 min-luz, e vai até encontrar o herói em x_H = 0.
            a, b = (CONTRACAO, 0), (0, CHEGADA)
            rot_pos, rot_dir = (CONTRACAO - V * 1.5, 1.5), RIGHT
        linha = Line(self.p(*a), self.p(*b), color=COR_TERRA, stroke_width=5)
        rot = Tex("Terra (espelho)", color=COR_TERRA, font_size=FS_ROTULO)
        rot.next_to(self.p(*rot_pos), rot_dir, buff=0.15)
        return VGroup(linha, rot)

    def heroi_origem(self):
        ponto = Dot(self.p(0, 0), color=COR_HEROI_ESCURO, radius=0.09)
        rot = Tex("Herói", color=COR_HEROI_ESCURO, font_size=FS_ROTULO)
        rot.next_to(self.p(0, 0), DL, buff=0.15)
        return VGroup(ponto, rot)

    # --- Linhas de mundo ----------------------------------------------------

    def tela(self, e):
        """Evento em coordenadas da Terra -> posição na tela, no referencial deste diagrama."""
        return self.p(*(e if self.obs == "T" else lorentz(*e)))

    def heroi_ida(self):
        """Herói da Emissão até o instante da Reflexão para a Terra (t_T = 8)."""
        return linha_heroi(self.tela(EVENTOS["Emissão"]), self.tela(HEROI_NA_REFLEXAO))

    def heroi_volta(self):
        return linha_heroi(self.tela(HEROI_NA_REFLEXAO), self.tela(EVENTOS["Colisão"]))

    def luz_ida(self):
        return Line(self.tela(EVENTOS["Emissão"]), self.tela(EVENTOS["Reflexão"]), color=COR_LUZ, stroke_width=4)

    def luz_volta(self):
        return Line(self.tela(EVENTOS["Reflexão"]), self.tela(EVENTOS["Colisão"]), color=COR_LUZ, stroke_width=4)

    # --- Eventos ------------------------------------------------------------

    LAYOUT = {  # direção do rótulo em relação ao ponto, por referencial
        "T": {"Emissão": UL, "Reflexão": UR, "Colisão": UL},  # Reflexão acima, porque embaixo passa o tracejado do S2b
        "H": {"Emissão": DL, "Reflexão": RIGHT, "Colisão": LEFT},  # UL cruzaria o eixo ct_T
    }

    def ponto_evento(self, nome):
        return Dot(self.tela(EVENTOS[nome]), color=COR_EVENTO, radius=0.08)

    def rotulo_evento(self, nome):
        """VGroup(nome, coords da Terra, coords do herói), já posicionado.

        Monta o grupo completo para que as coordenadas do herói, quando entram
        depois, não desloquem o nome nem as coordenadas da Terra.
        """
        terra = EVENTOS[nome]
        heroi = lorentz(*terra)
        direcao = self.LAYOUT[self.obs][nome]
        alinhar = RIGHT if direcao[0] < 0 else LEFT
        texto = Tex(nome, color=COR_EVENTO, font_size=FS_ROTULO)
        if np.allclose(terra, heroi):
            # mesmas coordenadas nos dois referenciais, então uma linha só, na cor do texto
            c_t = MathTex(par(*terra), color=COR_EVENTO, font_size=FS_COORD)
            c_h = VGroup()
        else:
            c_t = MathTex(par(*terra), color=COR_TERRA, font_size=FS_COORD)
            c_h = MathTex(par(*heroi), color=COR_HEROI, font_size=FS_COORD)
            if self.obs == "H":
                c_t, c_h = c_h, c_t  # no diagrama do herói, as coordenadas dele vêm primeiro
        VGroup(texto, c_t, c_h).arrange(DOWN, buff=0.08, aligned_edge=alinhar)
        grupo = VGroup(texto, c_t, c_h)
        grupo.next_to(self.tela(terra), direcao, buff=0.15)
        return grupo

    # --- Eixos oblíquos -------------------------------------------------------

    def eixo(self, w, tempo, cor, a=1.0, textos=True):
        """Eixo ct (tempo=True) ou x de um referencial que anda a w neste diagrama.

        `a` escolhe o estilo. Com 1 o eixo é oblíquo, só no sentido positivo e com a
        ponta recuada da borda. Com 0 é como o `Axes`, reta inteira e ponta na borda.
        O boost usa os valores do meio. Devolve VGroup(linhas e marcas, números, rótulo).
        """
        d = np.array([w, 1.0]) if tempo else np.array([1.0, w])
        s_fim = clip_raio(d, self.jan) - a * (0.6 if tempo else 0.15)
        s_neg = clip_raio(-d, self.jan)
        o, fim = self.p(0, 0), self.p(*(s_fim * d))
        linhas = VGroup(Line(o, fim, color=cor, stroke_width=2.5).add_tip(tip_length=0.18, tip_width=0.18))
        if a < 1:
            linhas.add(Line(o, self.p(*(-s_neg * d)), color=cor, stroke_width=2.5, stroke_opacity=1 - a))
        normal = rotate_vector(normalize(fim - o), PI / 2 if tempo else -PI / 2)
        numeros = VGroup()
        # uma marca por unidade própria do referencial, em (0, n) ou (n, 0) nele
        for n in range(-15, 16):
            xt = lorentz_inv(0, n, w) if tempo else lorentz_inv(n, 0, w)
            s = np.dot(xt, d) / np.dot(d, d)
            if n == 0 or s > s_fim - 0.3 or (n < 0 and (a >= 1 or -s > s_neg)):
                continue
            ponto = self.p(*xt)
            meia = 0.06 + 0.01 * a
            opac = 1 if n > 0 else 1 - a
            linhas.add(Line(ponto - normal * meia, ponto + normal * meia, color=cor, stroke_width=2.5 - 0.5 * a, stroke_opacity=opac))
            livre = all(np.linalg.norm(ponto - self.tela(ev)) > 0.3 for ev in EVENTOS.values())
            if textos and n > 0 and n % 2 == 0 and livre:
                numeros.add(MathTex(str(n), color=cor, font_size=FS_NUM).move_to(ponto + normal * 0.25))
        if not textos:
            return VGroup(linhas, numeros, VGroup())
        simbolo = ("ct_" if tempo else "x_") + ("H" if cor == COR_HEROI else "T")
        lado = UP if tempo and w < 0 else RIGHT  # com o ct apontando para a esquerda, o rótulo vai acima da ponta
        rot = MathTex(simbolo, color=cor, font_size=34).next_to(fim, lado, buff=0.1)
        return VGroup(linhas, numeros, rot)

    def eixos_obliquos(self, w, cor, numeros=True):
        grupo = VGroup()
        for tempo in (True, False):
            linhas, nums, rot = self.eixo(w, tempo, cor)
            grupo.add(linhas, *(nums if numeros else []), rot)
        return grupo

    def eixos_heroi(self, v, numeros=True):
        return self.eixos_obliquos(v, COR_HEROI, numeros)

    def grade_heroi(self, v, passo=1):
        """Linhas de localidade (x_H = k) e simultaneidade (t_H = k) do herói."""
        grade = VGroup()
        for k in range(-12, 16, passo):
            for p, d in [(lorentz_inv(k, 0, v), (v, 1)), (lorentz_inv(0, k, v), (1, v))]:
                seg = clip_reta(p, d, self.jan)
                if seg:
                    grade.add(Line(self.p(*seg[0]), self.p(*seg[1]), color=COR_HEROI, stroke_width=1.2, stroke_opacity=0.35))
        return grade

    def projecoes_heroi(self, nome):
        """Tracejados de um evento até os eixos do herói (paralelos ao outro eixo)."""
        terra = EVENTOS[nome]
        xh, th = lorentz(*terra)
        alvo_t = lorentz_inv(0, th)  # no eixo ct_H
        alvo_x = lorentz_inv(xh, 0)  # no eixo x_H
        origem = self.p(*terra)
        kw = dict(color=COR_HEROI, stroke_width=2, dash_length=0.08)
        return VGroup(DashedLine(origem, self.p(*alvo_t), **kw), DashedLine(origem, self.p(*alvo_x), **kw))

    # --- Instante da Reflexão (S2b) ------------------------------------------

    def instante_reflexao(self):
        """Instante da Reflexão, t_T = 8, em verde, para comparar os tempos.

        - Tracejado horizontal em t_T = 8, da Reflexão até a linha do herói. É o "mesmo
          instante" para a Terra, e ali o relógio do herói marca 6,4.
        - Tracejado vertical desse ponto até o eixo x_T, com 4,8. É onde o herói está,
          para a Terra, no instante da Reflexão.
        - À esquerda do ponto, as coordenadas dele na Terra, (4,8, 8).
        """
        x_h, t = HEROI_NA_REFLEXAO
        kw = dict(color=COR_DESTAQUE, stroke_width=3, dash_length=0.1)

        ponto = Dot(self.p(x_h, t), color=COR_HEROI_ESCURO, radius=0.08)
        # à direita da linha do herói e abaixo do tracejado, porque à esquerda ficam os
        # números do eixo ct_H e acima passa o próprio eixo
        t_heroi = MathTex(num(lorentz(x_h, t)[1]), color=COR_DESTAQUE, font_size=FS_COORD)
        t_heroi.next_to(ponto, RIGHT, buff=0.12).shift(0.22 * DOWN)

        mesmo_instante = DashedLine(self.p(*EVENTOS["Reflexão"]), self.p(x_h, t), **kw)
        vertical = DashedLine(self.p(x_h, t), self.p(x_h, 0), **kw)
        # na fileira dos números do eixo x_T, entre o 4 e o 6
        x_heroi = MathTex(num(x_h), color=COR_DESTAQUE, font_size=FS_COORD)
        x_heroi.move_to([self.p(x_h, 0)[0], self.ax.x_axis.numbers[0].get_y(), 0])

        # à esquerda e um pouco acima, porque embaixo passa a linha do herói
        coords = MathTex(par(x_h, t), color=COR_DESTAQUE, font_size=FS_COORD)
        coords.next_to(ponto, LEFT, buff=0.15).shift(0.12 * UP)

        return SimpleNamespace(
            ponto=ponto, t_heroi=t_heroi, mesmo_instante=mesmo_instante, vertical=vertical, x_heroi=x_heroi,
            coords=coords,
        )

    # --- Simultaneidade -----------------------------------------------------

    def linha_simultaneidade(self, s):
        """Segmento da origem até a Terra ao longo de t = s·x, a simultaneidade de quem anda a v = s."""
        seg = Line(self.p(0, 0), self.p(DIST, s * DIST), color=COR_DESTAQUE, stroke_width=5)
        ponto = Dot(self.p(DIST, s * DIST), color=COR_DESTAQUE, radius=0.08)
        return VGroup(seg, ponto)

    def rotulo_comprimento(self, s, texto):
        a, b = self.p(0, 0), self.p(DIST, s * DIST)
        rot = MathTex(texto, color=COR_DESTAQUE, font_size=FS_COORD)
        ang = np.arctan2(b[1] - a[1], b[0] - a[0])
        rot.rotate(ang).move_to((a + b) / 2 + rotate_vector(RIGHT, ang + PI / 2) * 0.28)
        return rot


# =============================================================================
# Estados
# =============================================================================


class Estados:
    """Os estados S0 a S3 do diagrama da Terra, criando cada mobject uma vez só.

    Cada `sN()` devolve uma lista de mobjects, e a ordem da lista é a ordem das
    camadas: o primeiro fica no fundo. Uma transição começa com `self.add(*E.sN())`
    e termina com a cena igual a `E.sN+1()`.
    """

    def __init__(self):
        D = self.D = Diagrama("T")
        self.eixos = D.eixos()
        self.terra = D.linha_terra()
        self.heroi = D.heroi_origem()
        self.heroi_ida, self.heroi_volta = D.heroi_ida(), D.heroi_volta()
        self.luz_ida, self.luz_volta = D.luz_ida(), D.luz_volta()
        self.pontos = {n: D.ponto_evento(n) for n in EVENTOS}
        self.rotulos = {n: D.rotulo_evento(n) for n in EVENTOS}
        self.eixos_heroi = D.eixos_heroi(V)
        self.projecoes = D.projecoes_heroi("Reflexão")
        self.instante = D.instante_reflexao()

    def nome(self, n):
        return self.rotulos[n][0]

    def coords_terra(self):
        return VGroup(*(r[1] for r in self.rotulos.values()))

    def coords_heroi(self):
        return VGroup(*(r[2] for r in self.rotulos.values()))

    def coords(self, n):
        """Coordenadas do evento nos dois referenciais (na Emissão, uma linha só)."""
        return VGroup(*self.rotulos[n][1:])

    def s0(self):
        return [self.eixos, self.terra, self.heroi]

    def s1(self):
        # eixos do herói entram atrás das linhas de mundo e dos eventos
        return self.s0() + [self.eixos_heroi]

    def s2(self):
        # Reflexão só com as coordenadas da Terra, e as do herói entram no S2c
        return self.s1() + [
            self.heroi_ida, self.luz_ida,
            self.pontos["Emissão"], self.nome("Emissão"), self.coords("Emissão"),
            self.pontos["Reflexão"], self.nome("Reflexão"), self.rotulos["Reflexão"][1],
        ]  # fmt: skip

    def s2b(self):
        # tracejados verdes atrás das linhas de mundo, ponto e número por cima
        I = self.instante
        fundo = [I.mesmo_instante, I.vertical]
        return self.s2()[:4] + fundo + self.s2()[4:] + [I.ponto, I.t_heroi, I.x_heroi, I.coords]

    def s2c(self):
        # sem o verde, com as projeções logo depois dos eixos do herói e as coordenadas dele na Reflexão
        return self.s2()[:4] + [self.projecoes] + self.s2()[4:] + [self.rotulos["Reflexão"][2]]

    def instante_tudo(self):
        I = self.instante
        return VGroup(I.mesmo_instante, I.vertical, I.ponto, I.t_heroi, I.x_heroi, I.coords)

    def s3(self):
        return self.s2c() + [
            self.heroi_volta, self.luz_volta,
            self.pontos["Colisão"], self.nome("Colisão"), self.coords("Colisão"),
        ]  # fmt: skip


# =============================================================================
# Boost de Lorentz: do diagrama da Terra (S3) para o referencial do herói
# =============================================================================


class Boost:
    """O mesmo espaço-tempo desenhado num referencial que anda a u em relação à Terra.

    A janela também vai de JANELA_T para JANELA_H, para dar espaço aos eixos da
    Terra quando eles abrem.

    Em `quadro(a)`, a é a fração da rapidez do herói. Com a = 0 o quadro é o S3 sem
    os textos dos eixos, as coordenadas e os rótulos "Herói" e "Terra (espelho)".
    Com a = 1 é o referencial do herói, com os eixos dele ortogonais e os da Terra
    abertos para fora. Os nomes dos eventos andam com o ponto, e a distância até ele
    vai da posição final num referencial à posição final no outro. Os rótulos das
    linhas de mundo cruzariam os dos eventos no caminho, então somem antes do boost
    e voltam já no lugar final.
    """

    T_ROT_HEROI = 5  # t_H do rótulo "Herói" no fim. Na origem ele ficaria entre os eixos da Terra.

    def __init__(self):
        self.DT, self.DH = Diagrama("T", JANELA_T), Diagrama("H", JANELA_H)
        self.phi = atanh(V)

        self.nomes, self.desloc = {}, {}
        for n in EVENTOS:
            nome_t, nome_h = self.DT.rotulo_evento(n)[0], self.DH.rotulo_evento(n)[0]
            self.nomes[n] = nome_t
            self.desloc[n] = (nome_t.get_center() - self.DT.tela(EVENTOS[n]), nome_h.get_center() - self.DH.tela(EVENTOS[n]))

    def rotulo_heroi_final(self):
        # à esquerda dos números do eixo ct_H
        return Tex("Herói", color=COR_HEROI_ESCURO, font_size=FS_ROTULO).next_to(self.DH.p(0, self.T_ROT_HEROI), LEFT, buff=0.45)

    def quadro(self, a):
        """Mobjects na ordem das camadas do S3."""
        u = np.tanh(a * self.phi)
        jan = JANELA_T.interpola(JANELA_H, a)
        D, p = Diagrama("T", jan), jan.p

        def P(x, t):  # coordenadas da Terra -> tela, no referencial u
            return p(*lorentz(x, t, u))

        def evento(n):
            ponto = P(*EVENTOS[n])
            nome = self.nomes[n].copy().move_to(ponto + lerp(*self.desloc[n], a))
            return Dot(ponto, color=COR_EVENTO, radius=0.08), nome

        w_heroi = velocidade_relativa(V, u)  # velocidade do herói vista do referencial u
        eixos_t = VGroup(*(D.eixo(-u, tempo, COR_TERRA, a, textos=False)[0] for tempo in (True, False)))
        eixos_h = VGroup(*(D.eixo(w_heroi, tempo, COR_HEROI, 1 - a, textos=False)[0] for tempo in (True, False)))

        # Terra a partir de t = 0 do referencial desenhado, até a borda ou até x = 0
        x0 = DIST / gamma(u)  # a distância até a Terra, contraída no referencial u
        t_fim = min(jan.t_max, x0 / u) if u > 1e-9 else jan.t_max
        terra = Line(p(x0, 0), p(x0 - u * t_fim, t_fim), color=COR_TERRA, stroke_width=5)

        heroi = Dot(p(0, 0), color=COR_HEROI_ESCURO, radius=0.09)

        em, re, co = EVENTOS.values()
        return VGroup(
            eixos_t, terra, heroi, eixos_h,
            linha_heroi(P(*em), P(*HEROI_NA_REFLEXAO)),
            Line(P(*em), P(*re), color=COR_LUZ, stroke_width=4),
            *evento("Emissão"), *evento("Reflexão"),
            linha_heroi(P(*HEROI_NA_REFLEXAO), P(*co)),
            Line(P(*re), P(*co), color=COR_LUZ, stroke_width=4),
            *evento("Colisão"),
        )  # fmt: skip

    def textos_final(self):
        """Números e rótulos dos eixos, coordenadas do herói e rótulos das linhas de mundo, no referencial dele."""
        D = self.DH
        eixos_terra = VGroup(*(VGroup(*D.eixo(-V, tempo, COR_TERRA)[1:]) for tempo in (True, False)))
        coords = VGroup(*(D.rotulo_evento(n)[1] for n in EVENTOS))
        return VGroup(D.ax.x_axis.numbers, D.ax.y_axis.numbers, D.rot_x, D.rot_t, eixos_terra, coords, D.linha_terra()[1], self.rotulo_heroi_final())

    def simetria(self):
        """Tracejados verdes da Reflexão até os eixos do herói. O de t_H = 4 marca a metade
        da ida e volta, já que a luz gasta o mesmo tempo para ir e para voltar. O de
        x_H = 4 marca onde a reflexão acontece."""
        x, t = lorentz(*REFLEXAO)  # (4, 4): t_H = 4 é a metade da ida e volta
        p, kw = self.DH.p, dict(color=COR_DESTAQUE, stroke_width=3, dash_length=0.1)
        return VGroup(DashedLine(p(0, t), p(x, t), **kw), DashedLine(p(x, 0), p(x, t), **kw))


# =============================================================================
# Ecos: o herói reemite a luz cada vez que ela volta, no referencial dele
# =============================================================================


class Ecos:
    """Diagrama do herói em que ele reemite a luz a cada retorno, até a Terra chegar.

    `quadro(T)` desenha tudo o que já aconteceu até t_H = T: linha do herói, luz em
    zigue-zague, os retornos e as cotas dos Δt crescendo como cronômetros.
    """

    N_ECOS = 7  # depois do 5º o zigue-zague já não se vê
    N_COTAS = 3  # 8, 2 e 0,5 min. A próxima, de 0,125, não cabe.
    X_COTA = -2.0

    def __init__(self):
        self.D = D = Diagrama("H", JANELA_E)
        self.ecos = lista_ecos(self.N_ECOS)
        self.t_fim = CHEGADA
        self.eixos = D.eixos()
        self.terra = D.linha_terra()
        self.heroi = D.heroi_origem()
        self.emissao = Dot(D.p(0, 0), color=COR_EVENTO, radius=0.08)
        self.chegada = Dot(D.p(0, self.t_fim), color=COR_EVENTO, radius=0.08)
        # à direita e só um pouco acima: embaixo chega a linha da Terra e mais acima fica o rótulo do eixo ct_H
        self.rot_chegada = Tex("Chegada", color=COR_EVENTO, font_size=FS_ROTULO)
        self.rot_chegada.next_to(self.chegada, RIGHT, buff=0.2).shift(0.12 * UP)
        self.rot_cotas = VGroup(*(
            MathTex(rf"{num(dt)}\ \text{{min}}", color=COR_DESTAQUE, font_size=FS_COORD)
            .next_to(D.p(self.X_COTA, t + dt / 2), LEFT, buff=0.15)
            for t, _, dt in self.ecos[: self.N_COTAS]
        ))  # fmt: skip

    def inicio(self):
        return [self.eixos, self.terra, self.heroi, self.emissao]

    def fim(self):
        return self.inicio()[:-1] + [self.quadro(self.t_fim), self.emissao, self.chegada, self.rot_chegada, self.rot_cotas]

    def cota(self, t0, t1):
        p, meia = self.D.p, 0.1 * RIGHT
        a, b = p(self.X_COTA, t0), p(self.X_COTA, t1)
        kw = dict(color=COR_DESTAQUE, stroke_width=3)
        return VGroup(Line(a, b, **kw), Line(a - meia, a + meia, **kw), Line(b - meia, b + meia, **kw))

    def quadro(self, T):
        p = self.D.p
        T = min(T, self.t_fim)
        luz, retornos, cotas = VGroup(), VGroup(), VGroup()
        for i, (t, x, dt) in enumerate(self.ecos):
            if T <= t:
                break
            meio = dt / 2  # a luz encontra o espelho na metade do tempo, em x_H = dt/2
            pts = [(0, t), (meio, t + meio)]
            if T < t + meio:
                pts[1] = (T - t, T)
            elif T < t + dt:
                pts.append((dt - (T - t), T))
            else:
                pts.append((0, t + dt))
                retornos.add(Dot(p(0, t + dt), color=COR_EVENTO, radius=0.06))
            luz.add(*(Line(p(*a), p(*b), color=COR_LUZ, stroke_width=4) for a, b in zip(pts, pts[1:])))
            if i < self.N_COTAS:
                cotas.add(self.cota(t, min(T, t + dt)))
        heroi = linha_heroi(p(0, 0), p(0, T)) if T > 1e-6 else VGroup()
        return VGroup(cotas, heroi, luz, retornos)


# #############################################################################
# Cenas
# #############################################################################

# =============================================================================
# Contexto, antes dos diagramas
# =============================================================================


class C_Contexto(Scene):
    """Contexto em 1D, sem tempo, com as posições no instante da Emissão em cada referencial.

    Terra (t_T = 0): herói em x_T = 0 indo a v, espelho parado em x_T = 8.
    Herói (t_H = 0): herói parado em x_H = 0, espelho vindo a v de x_H = 6,4.
    O eixo x usa a janela e a escala dos diagramas e fica alinhado com o x_T do S0.
    """

    R_TERRA = 0.32  # raio do desenho da Terra, em unidades de tela
    SETA = 1.0  # comprimento das setas de velocidade, em unidades de tela

    def construct(self):
        self.add(self.painel("T", 1.91, DIST), self.painel("H", -1.69, CONTRACAO))
        self.wait(0.1)

    def painel(self, obs, y0, x_terra):
        j = JANELA_T
        cor = COR_TERRA if obs == "T" else COR_HEROI
        eixo = NumberLine(
            x_range=[j.x_min, j.x_max, 1],
            length=(j.x_max - j.x_min) * j.u,
            color=cor,
            stroke_width=2.5,
            include_tip=True,
            tip_width=0.18,
            tip_height=0.18,
            tick_size=0.06,
        )
        eixo.shift(np.array([j.canto[0], y0, 0]) - eixo.n2p(j.x_min))
        rot_eixo = rotulo_eixo(f"x_{obs}", cor).next_to(eixo.n2p(j.x_max), RIGHT, buff=0.15)
        p = eixo.n2p  # número na reta -> posição na tela

        nome_ref = "da Terra" if obs == "T" else "do herói"
        titulo = VGroup(
            Tex(f"Referencial {nome_ref}", color=cor, font_size=36),
            MathTex(rf"t_{obs} = 0", color=cor, font_size=FS_COORD),
        ).arrange(RIGHT, buff=0.35, aligned_edge=DOWN)
        titulo.move_to(np.array([j.canto[0], y0 + 1.25, 0]), aligned_edge=LEFT)

        # herói, um ponto na origem
        heroi = Dot(p(0), color=COR_HEROI_ESCURO, radius=0.1)
        nome_heroi = Tex("Herói", color=COR_HEROI_ESCURO, font_size=FS_ROTULO).next_to(p(0), UP, buff=0.3)

        # Terra: o espelho é uma barra em x_terra, com o planeta logo atrás
        espelho = Line(p(x_terra) + 0.45 * DOWN, p(x_terra) + 0.45 * UP, color=COR_TEXTO, stroke_width=7)
        planeta = Circle(radius=self.R_TERRA, color=COR_TERRA, fill_opacity=1, stroke_width=0)
        planeta.move_to(p(x_terra) + (self.R_TERRA + 0.03) * RIGHT)
        nome_terra = Tex("Terra (espelho)", color=COR_TERRA, font_size=FS_ROTULO)
        nome_terra.next_to(VGroup(espelho, planeta), UP, buff=0.12)

        # a seta de velocidade vai em quem se move, e isso depende do referencial
        if obs == "T":
            movel, sentido, lado = nome_heroi, RIGHT, RIGHT
        else:
            movel, sentido, lado = nome_terra, LEFT, LEFT
        cor_movel = COR_HEROI_ESCURO if obs == "T" else COR_TERRA
        inicio = movel.get_edge_center(lado) + 0.2 * lado
        seta = Arrow(
            inicio, inicio + self.SETA * sentido, buff=0, color=cor_movel, stroke_width=4,
            tip_length=0.18, max_tip_length_to_length_ratio=1,
        )
        rot_v = MathTex(rf"{num(V)}\,c", color=cor_movel, font_size=FS_COORD).next_to(seta, sentido, buff=0.12)

        # coordenadas no referencial do painel
        coords = VGroup(*(
            MathTex(rf"x_{obs} = {num(x)}", color=cor, font_size=FS_COORD).move_to(p(x) + 0.75 * DOWN)
            for x in (0, x_terra)
        ))  # fmt: skip

        # distância entre o herói e o espelho
        y_cota = y0 - 1.15
        a, b = np.array([p(0)[0], y_cota, 0]), np.array([p(x_terra)[0], y_cota, 0])
        cota = VGroup(
            DoubleArrow(a, b, buff=0, color=COR_DESTAQUE, stroke_width=3, tip_length=0.15, max_tip_length_to_length_ratio=1),
            Line(a + 0.12 * DOWN, a + 0.12 * UP, color=COR_DESTAQUE, stroke_width=3),
            Line(b + 0.12 * DOWN, b + 0.12 * UP, color=COR_DESTAQUE, stroke_width=3),
        )
        rot_cota = MathTex(rf"{num(x_terra)}\ \text{{min-luz}}", color=COR_DESTAQUE, font_size=FS_COORD)
        rot_cota.next_to(cota, DOWN, buff=0.1)

        return VGroup(
            titulo, eixo, rot_eixo, cota, rot_cota, coords,
            espelho, planeta, nome_terra, heroi, nome_heroi, seta, rot_v,
        )  # fmt: skip


# =============================================================================
# Diagrama da Terra, de S0 a S5
# =============================================================================


class Base(Scene):
    def setup(self):
        self.E = Estados()


class S0_Base(Base):
    def construct(self):
        self.add(*self.E.s0())
        self.wait(0.1)


class S1_EixosHeroi(Base):
    def construct(self):
        E = self.E
        self.add(*E.s0())
        # a velocidade dos eixos vai de 0 a 0,6, e a grade e os eixos são redesenhados a cada quadro
        v = ValueTracker(0)
        grade = always_redraw(lambda: E.D.grade_heroi(v.get_value()))
        eixos = always_redraw(lambda: E.D.eixos_heroi(v.get_value(), numeros=False))
        self.wait(0.2)
        self.play(FadeIn(grade), FadeIn(eixos), run_time=0.5)
        self.bring_to_front(E.terra, E.heroi)
        self.play(v.animate.set_value(V), run_time=2.5, rate_func=smooth)
        grade.clear_updaters()
        self.remove(eixos)
        self.add(*E.s1())  # reordena as camadas como no S1, com a grade atrás
        self.play(FadeOut(grade), run_time=0.6)
        self.wait(0.3)


class S2_Reflexao(Base):
    def construct(self):
        E = self.E
        self.add(*E.s1())
        self.wait(0.3)
        self.play(
            FadeIn(E.pontos["Emissão"], scale=2),
            Flash(E.D.p(0, 0), color=COR_LUZ, line_length=0.25, flash_radius=0.2),
            FadeIn(E.nome("Emissão")),
            FadeIn(E.coords("Emissão")),
            run_time=0.6,
        )
        # herói e luz crescem juntos: com rate_func=linear a ponta dos dois está no mesmo t_T a cada quadro.
        # lag_ratio=0 desenha o contorno branco e a linha do herói ao mesmo tempo.
        self.play(Create(E.heroi_ida, lag_ratio=0), Create(E.luz_ida), rate_func=linear, run_time=2.4)
        self.play(
            FadeIn(E.pontos["Reflexão"], scale=2),
            Flash(E.D.p(*REFLEXAO), color=COR_LUZ, line_length=0.25, flash_radius=0.2),
            FadeIn(E.nome("Reflexão")),
            run_time=0.6,
        )
        self.play(FadeIn(E.rotulos["Reflexão"][1], shift=0.1 * UP), run_time=0.5)  # coordenadas da Terra
        self.wait(0.3)


class S2b_InstanteReflexao(Base):
    def construct(self):
        E = self.E
        I = E.instante
        self.add(*E.s2())
        self.wait(0.2)
        # Tracejado da Reflexão até o herói, no 6,4, e dali vertical até o eixo x_T, no 4,8.
        # Cada parte só entra na cena quando vai ser animada, e já na camada final,
        # porque play não reordena o que já está na cena.
        mostrados = set(E.s2())

        def entra(*novos):
            mostrados.update(novos)
            self.add(*(m for m in E.s2b() if m in mostrados))

        entra(I.mesmo_instante)
        self.play(Create(I.mesmo_instante), run_time=0.7)
        entra(I.ponto, I.t_heroi)
        self.play(FadeIn(I.ponto, scale=2), FadeIn(I.t_heroi), run_time=0.5)
        entra(I.vertical)
        self.play(Create(I.vertical), run_time=0.8)
        entra(I.x_heroi)
        self.play(FadeIn(I.x_heroi), run_time=0.4)
        entra(I.coords)
        self.play(FadeIn(I.coords, shift=0.1 * LEFT), run_time=0.5)
        self.wait(0.4)


class S2c_CoordsHeroi(Base):
    def construct(self):
        E = self.E
        self.add(*E.s2b())
        self.wait(0.2)
        self.play(FadeOut(E.instante_tudo()), run_time=0.5)  # o verde sai antes das coordenadas do herói
        # projeções já na camada delas, atrás das linhas de mundo, porque play não reordena o que já está na cena
        coords = E.rotulos["Reflexão"][2]
        self.add(*(m for m in E.s2c() if m is not coords))
        self.play(*(Create(l) for l in E.projecoes), FadeIn(coords, shift=0.1 * UP), run_time=0.9)
        self.wait(0.3)


class S3_Colisao(Base):
    def construct(self):
        E = self.E
        self.add(*E.s2c())
        self.wait(0.2)
        self.play(Create(E.heroi_volta, lag_ratio=0), Create(E.luz_volta), rate_func=linear, run_time=0.9)
        self.play(
            FadeIn(E.pontos["Colisão"], scale=2),
            Flash(E.D.p(*COLISAO), color=COR_LUZ, line_length=0.25, flash_radius=0.2),
            FadeIn(E.nome("Colisão")),
            run_time=0.6,
        )
        self.play(FadeIn(E.coords("Colisão"), shift=0.1 * UP), run_time=0.6)
        self.wait(0.3)


class S5_Simultaneidade(Base):
    def construct(self):
        E, D = self.E, self.E.D
        self.add(*E.s3())
        # a inclinação da linha vai de 0 (simultâneo para a Terra) a v (simultâneo para o herói)
        s = ValueTracker(0)
        linha = always_redraw(lambda: D.linha_simultaneidade(s.get_value()))
        rot_8 = D.rotulo_comprimento(0, rf"{num(DIST)}\ \text{{min-luz}}")
        rot_64 = D.rotulo_comprimento(V, rf"{num(CONTRACAO)}\ \text{{min-luz}}")
        rot_t = MathTex(rf"t_T = {num(SIMULTANEIDADE)}", color=COR_DESTAQUE, font_size=FS_COORD)
        rot_t.next_to(D.p(DIST, SIMULTANEIDADE), RIGHT, buff=0.22)

        self.wait(0.2)
        self.play(Create(linha), FadeIn(rot_8), run_time=0.7)
        self.play(FadeOut(rot_8, run_time=0.4), s.animate.set_value(V), run_time=2.2, rate_func=smooth)
        linha.clear_updaters()
        self.play(FadeIn(rot_64), FadeIn(rot_t), run_time=0.6)
        self.wait(0.3)


# =============================================================================
# Boost de Lorentz até o referencial do herói, e dilatação
# =============================================================================


class R_RefHeroi(Base):
    """S3 -> referencial do herói por um boost de Lorentz. No fim entram os tracejados verdes da Reflexão."""

    def construct(self):
        E, B = self.E, Boost()
        ax = E.eixos[0]
        textos = VGroup(
            ax.x_axis.numbers, ax.y_axis.numbers, E.eixos[1], E.eixos[2], E.terra[1], E.heroi[1],
            *(m for m in E.eixos_heroi if isinstance(m, MathTex)),
            E.coords_terra(), E.coords_heroi(), E.projecoes,
        )  # fmt: skip
        # a = fração da rapidez do herói: 0 é o diagrama da Terra, 1 é o do herói
        a = ValueTracker(0)
        quadro = always_redraw(lambda: B.quadro(a.get_value()))
        # Começa igual ao S3, com o quadro em a = 0, que tem as mesmas linhas, e os textos
        # por cima. Não dá para partir de E.s3() e apagar só os números, porque remover um
        # submobjeto do Axes faz a cena trocá-lo pelos filhos, e a linha do eixo some junto.
        self.add(quadro, textos)
        self.wait(0.3)
        self.play(FadeOut(textos), run_time=0.5)
        self.play(a.animate.set_value(1), run_time=2.6, rate_func=smooth)
        quadro.clear_updaters()
        self.play(FadeIn(B.textos_final()), run_time=0.5)
        simetria = B.simetria()
        self.add(simetria)
        self.bring_to_back(simetria)  # por baixo da linha do herói, do eixo x_H e do ponto da Reflexão
        self.play(Create(simetria), run_time=0.5)
        self.wait(0.3)


class D_Dilatacao(Base):
    """Hipérbole c²t² − x² = τ². A Colisão, com t_H = 8, e o ponto t_T = 8 no eixo da
    Terra estão à mesma "distância" da Emissão. A Colisão acontece em t_T = 10."""

    def construct(self):
        E, D = self.E, self.E.D
        t_T, t_H, tau = COLISAO[1], IDA_VOLTA, TEMPO_PROPRIO
        x_fim = COLISAO[0] + 0.4  # a hipérbole passa um pouco da Colisão

        def ramo(s):
            return D.p(tau * sinh(s), tau * cosh(s))

        hiperbole = ParametricFunction(ramo, t_range=[0, asinh(x_fim / tau)], color=COR_DESTAQUE, stroke_width=4)
        rot_hip = MathTex(rf"\tau = {num(tau)}\ \text{{min}}", color=COR_DESTAQUE, font_size=FS_COORD)
        rot_hip.next_to(D.p(1.6, tau - 0.15), DOWN, buff=0.1)
        marca = Dot(D.p(0, tau), color=COR_DESTAQUE, radius=0.08)
        tracejado = DashedLine(D.p(*COLISAO), D.p(0, t_T), color=COR_TERRA, stroke_width=2, dash_length=0.08)

        rot_col = VGroup(
            Tex("Colisão", color=COR_EVENTO, font_size=FS_ROTULO),
            VGroup(
                MathTex(rf"t_T = {num(t_T)}", color=COR_TERRA, font_size=FS_COORD),
                MathTex(rf"t_H = {num(t_H)}", color=COR_HEROI, font_size=FS_COORD),
            ).arrange(RIGHT, buff=0.3),
        ).arrange(DOWN, buff=0.08, aligned_edge=RIGHT)
        rot_col.next_to(D.p(*COLISAO), UL, buff=0.1).shift(0.25 * LEFT)

        fundo = E.s0() + [E.eixos_heroi, E.heroi_ida, E.heroi_volta, E.luz_ida, E.luz_volta]
        self.add(*fundo)
        self.add(hiperbole, tracejado, marca, E.pontos["Emissão"], E.pontos["Colisão"], rot_col, rot_hip)
        self.wait(0.1)


# =============================================================================
# Ecos: o herói reemite a luz cada vez que ela volta, no referencial dele
# =============================================================================


class G_TempoEco(Scene):
    """Δt_H da ida e volta da luz em função da distância x_H da Terra na emissão.

    No referencial do herói, a luz e o espelho se aproximam a 1 + v e a volta leva o
    mesmo tempo que a ida, então Δt = 2x/(1 + v). A reta sobe de 0, com a Terra
    encostada, até 8 em x = 6,4, no início. O gráfico marca os ecos do E_Ecos,
    que se acumulam perto de zero. Não é diagrama de Minkowski, então os eixos ficam
    na cor do texto. Só entram valores pontuais, e a equação fica no slide.
    """

    U = 0.6  # mesma escala nos dois eixos, um em min e o outro em min-luz
    T_MAX = 9.6

    def eixo_x(self):
        """Devolve os ecos como (x, Δt), os extremos da reta, os valores extras do eixo x e o rótulo do eixo."""
        ecos = [(x, dt) for _, x, dt in lista_ecos(5)]
        rot = Tex(r"distância da Terra\\na emissão\\(min-luz)", color=COR_TEXTO, font_size=24)
        return ecos, ((0, 0), (CONTRACAO, eco(CONTRACAO))), [], rot

    def construct(self):
        ecos, (r0, r1), extras, rot_x = self.eixo_x()
        x_max = max(r0[0], r1[0]) + 1
        ax = Axes(
            x_range=[0, x_max, 1],
            y_range=[0, self.T_MAX, 1],
            x_length=x_max * self.U,
            y_length=self.T_MAX * self.U,
            axis_config={"color": COR_TEXTO, "stroke_width": 2.5, "tip_width": 0.18, "tip_height": 0.18, "tick_size": 0.06},
        )
        rot_x.next_to(ax.x_axis.get_end(), RIGHT, buff=0.15)
        rot_t = VGroup(
            MathTex(r"\Delta t_H", color=COR_TEXTO, font_size=34),
            Tex("ida e volta (min)", color=COR_TEXTO, font_size=20),
        ).arrange(DOWN, buff=0.06)
        rot_t.next_to(ax.y_axis.get_end(), RIGHT, buff=0.2)
        grafico = VGroup(ax, rot_x, rot_t)

        # ax.c2p converte coordenadas do gráfico em posição na tela
        reta = Line(ax.c2p(*r0), ax.c2p(*r1), color=COR_DESTAQUE, stroke_width=4)
        pontos = VGroup(*(Dot(ax.c2p(x, dt), color=COR_EVENTO, radius=0.07) for x, dt in ecos))

        # tracejados e valores dos dois primeiros ecos. Um eco em x = 0 só ganha o Δt.
        kw = dict(color=COR_DESTAQUE, stroke_width=2.5, dash_length=0.08)
        verde = dict(color=COR_DESTAQUE, font_size=FS_COORD)
        guias, valores = VGroup(), VGroup()
        for x, dt in ecos[:2]:
            valores.add(MathTex(num(dt), **verde).next_to(ax.c2p(0, dt), LEFT, buff=0.15))
            if x > 1e-9:
                guias.add(DashedLine(ax.c2p(x, dt), ax.c2p(0, dt), **kw), DashedLine(ax.c2p(x, dt), ax.c2p(x, 0), **kw))
                valores.add(MathTex(num(x), **verde).next_to(ax.c2p(x, 0), DOWN, buff=0.15))
        for x in extras:
            valores.add(MathTex(num(x), **verde).next_to(ax.c2p(x, 0), DOWN, buff=0.15))

        VGroup(grafico, guias, reta, pontos, valores).move_to(ORIGIN)
        self.add(grafico, guias, reta, pontos, valores)
        self.wait(0.1)


class G_TempoEcoT(G_TempoEco):
    """Variante para comparar, com Δt_H em função do instante t_H da emissão.

    Δt = 2(6,4 − v·t)/(1 + v) = 8 − 0,75·t, uma reta de 8 em t = 0 até 0 na chegada,
    em t_H ≈ 10,67. Os ecos ficam em t = 0, 8, 10, 10,5…
    """

    def eixo_x(self):
        ecos = [(t, dt) for t, _, dt in lista_ecos(5)]
        rot = VGroup(
            MathTex("t_H", color=COR_TEXTO, font_size=34),
            Tex(r"emissão\\(min)", color=COR_TEXTO, font_size=20),
        ).arrange(DOWN, buff=0.06)
        return ecos, ((0, ecos[0][1]), (CHEGADA, 0)), [CHEGADA], rot


class E0_Ecos(Scene):
    def construct(self):
        self.add(*Ecos().inicio())
        self.wait(0.1)


class E_Ecos(Scene):
    """Luz em zigue-zague, com t_H avançando em ritmo constante. Cada ida e volta leva
    1/4 da anterior. As cotas crescem com o tempo e os valores entram no fim, junto
    com a Chegada."""

    SEG_POR_MIN = 0.42

    def construct(self):
        Z = Ecos()
        self.add(*Z.inicio())
        self.wait(0.2)
        # T é o t_H atual. Z.quadro(T) desenha tudo o que já aconteceu até ele.
        T = ValueTracker(0)
        quadro = always_redraw(lambda: Z.quadro(T.get_value()))
        self.add(quadro)
        self.add(Z.emissao)  # o ponto da Emissão fica por cima da linha do herói
        self.play(T.animate.set_value(Z.t_fim), run_time=Z.t_fim * self.SEG_POR_MIN, rate_func=linear)
        quadro.clear_updaters()
        self.remove(quadro)
        self.add(*Z.fim()[:-3])
        self.play(FadeIn(Z.chegada, scale=2), FadeIn(Z.rot_chegada), FadeIn(Z.rot_cotas), run_time=0.6)
        self.wait(0.3)


class R_Ecos(Scene):
    """R_RefHeroi -> estado final do E_Ecos.

    Somem os eixos da Terra, o verde, os nomes e as coordenadas dos eventos e o ponto
    da Reflexão. O diagrama passa de JANELA_H para JANELA_E redesenhando só as linhas,
    e os números, os rótulos e a primeira cota entram depois. Os ecos continuam a
    partir da Colisão, em t_H = 8, no ritmo do E_Ecos, e a cena termina igual a ele.
    """

    def construct(self):
        B, Z = Boost(), Ecos()
        quadro, textos, simetria = B.quadro(1), B.textos_final(), B.simetria()
        # achatado, na ordem do fim do R_RefHeroi, porque tirar um filho de um grupo que
        # está na cena faz o Manim reestruturar o grupo
        self.add(simetria, *quadro, *textos)
        eixos_t, terra, heroi, eixos_h, heroi_a, luz_a, p_em, n_em, p_re, n_re, heroi_b, luz_b, p_co, n_co = quadro
        num_x, num_t, rot_x, rot_t, eixos_terra, coords, rot_terra, rot_heroi = textos
        self.wait(0.3)

        # 1. some o que não é dos ecos, e a Colisão vira um retorno, com o ponto menor
        fora = [eixos_t, eixos_terra, simetria, n_em, n_re, n_co, coords, p_re, num_x, num_t, rot_x, rot_t, rot_heroi]
        retorno = Dot(p_co.get_center(), color=COR_EVENTO, radius=0.06)
        self.play(*(FadeOut(m) for m in fora), Transform(p_co, retorno), run_time=0.6)

        # 2. JANELA_H -> JANELA_E, redesenhando só as linhas
        _, _, dt = Z.ecos[0]
        a = ValueTracker(0)

        def janela():
            jan = JANELA_H.interpola(JANELA_E, a.get_value())
            return Diagrama("H", jan), jan.p

        def base():
            D, p = janela()
            eixos = VGroup(*(D.eixo(0, tempo, COR_HEROI, 0, textos=False)[0] for tempo in (True, False)))
            return VGroup(eixos, D.linha_terra(), Dot(p(0, 0), color=COR_HEROI_ESCURO, radius=0.09))

        def ida_volta():
            _, p = janela()
            luz = dict(color=COR_LUZ, stroke_width=4)
            return VGroup(
                linha_heroi(p(0, 0), p(0, dt)),
                Line(p(0, 0), p(dt / 2, dt / 2), **luz),
                Line(p(dt / 2, dt / 2), p(0, dt), **luz),
                Dot(p(0, dt), color=COR_EVENTO, radius=0.06),
                Dot(p(0, 0), color=COR_EVENTO, radius=0.08),
            )

        self.remove(eixos_h, terra, heroi, heroi_a, luz_a, p_em, heroi_b, luz_b, p_co, rot_terra)
        m_base, m_ida = always_redraw(base), always_redraw(ida_volta)
        self.add(m_base, m_ida)
        self.play(a.animate.set_value(1), run_time=1.2, rate_func=smooth)
        m_base.clear_updaters()
        m_ida.clear_updaters()

        # 3. números e rótulos dos eixos, "Herói" na origem e a primeira cota, já completa
        cota = Z.cota(0, dt)
        novos = VGroup(Z.D.ax.x_axis.numbers, Z.D.ax.y_axis.numbers, Z.D.rot_x, Z.D.rot_t, Z.heroi[1], cota, Z.rot_cotas[0])
        self.play(FadeIn(novos), run_time=0.5)

        # 4. ecos a partir da Colisão, como no E_Ecos
        T = ValueTracker(dt)
        ecos = always_redraw(lambda: Z.quadro(T.get_value()))
        self.remove(m_ida, cota)
        self.add(ecos, Z.emissao)
        self.play(T.animate.set_value(Z.t_fim), run_time=(Z.t_fim - dt) * E_Ecos.SEG_POR_MIN, rate_func=linear)
        ecos.clear_updaters()
        self.play(FadeIn(Z.chegada, scale=2), FadeIn(Z.rot_chegada), FadeIn(Z.rot_cotas[1:]), run_time=0.6)

        # mesmas camadas do fim do E_Ecos
        self.clear()
        self.add(*Z.fim())
        self.wait(0.3)
