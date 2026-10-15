# Contexto da aula

Este arquivo reúne o que o grupo decidiu até agora, para que outra pessoa ou outra sessão de agente continue o trabalho sem ler o histórico. Antes de mudar qualquer coisa, leia o `perfil.md`, as regras das figuras e as regras para escrever uma transição, na seção Código. Elas valem para toda cena nova e para qualquer ajuste.

## O projeto

A disciplina é Introdução à Teoria da Relatividade, do 6º semestre de Engenharia do Insper. Até agora o curso cobriu só relatividade restrita. O grupo precisa montar uma situação em que a relatividade tenha efeito considerável e analisá-la com a formulação vista em aula.

A entrega é uma apresentação de 10 minutos em PowerPoint. O grupo não entrega o código, que só existe para gerar as figuras e os vídeos dos slides.

As animações apoiam a fala e nada mais. A apresentação tem que funcionar só com as imagens estáticas, e as animações são transições curtas entre elas. Nada de vídeo explicativo no estilo 3Blue1Brown. O contexto e as equações ficam nos slides.

## Física

Um herói está a 8 minutos-luz da Terra e voa a 0,6c em direção a um grande espelho que fica na Terra. Ele emite um raio de luz, que reflete no espelho e volta até ele.

As convenções são as das aulas, com a notação de subscritos da Aula 12:

- c = 1. Tempo em minutos, distância em minutos-luz, e o eixo vertical é ct.
- S = Terra, coordenadas (x_T, t_T). S' = herói, coordenadas (x_H, t_H).
- O herói passa pela origem em t_T = t_H = 0 e anda no sentido +x. A Terra fica parada em x_T = 8.
- Os 8 min-luz são a distância no referencial da Terra.
- v = 0,6, então γ = 1,25.
- Lorentz: x_H = γ(x_T − v t_T) e t_H = γ(t_T − v x_T). As inversas são iguais, com +v no lugar de −v.

Eventos:

| Evento   | Terra (x_T, t_T) | Herói (x_H, t_H) |
|----------|------------------|------------------|
| Emissão  | (0, 0)           | (0, 0)           |
| Reflexão | (8, 8)           | (4, 4)           |
| Colisão  | (6, 10)          | (0, 8)           |

O grupo chamou de "Colisão" o reencontro da luz refletida com o herói.

A apresentação tem estas análises. `equacoes()`, em `fisica.py`, calcula todas, e `test_fisica.py` confere os valores:

1. Coordenadas dos eventos por Lorentz, nos dois sentidos.
2. Intervalo invariante c²Δt² − Δx² entre cada par de eventos. Emissão→Reflexão e Reflexão→Colisão são tipo luz, com intervalo 0. Emissão→Colisão é tipo tempo, com intervalo 64 e tempo próprio de 8 min.
3. Dilatação do tempo. Da Emissão à Colisão passam 10 min na Terra e 8 min para o herói.
4. Contração. Para o herói, a distância até a Terra em t_H = 0 é 8/γ = 6,4 min-luz.
5. Simultaneidade. Para o herói, no instante da Emissão o relógio da Terra marca t_T = v·d = 4,8 min.
6. Radar. O herói mede 8 min de ida e volta e conclui que a Reflexão aconteceu em t_H = 4, a 4 min-luz dele. Lorentz dá o mesmo resultado.
7. Ecos, no referencial do herói. Se o espelho está em x_H no instante da emissão, a luz e o espelho se aproximam a 1 + v, e a volta leva o mesmo tempo que a ida. Então Δt_H = 2x_H/(1 + v) = 1,25·x_H, e com x_H = 6,4 dá Δt_H = 8. **Esse 1,25 não é o γ**, e é fácil confundir. Ele vem de 2/(1 + v) e só coincide com γ porque v = 0,6. Se o herói reemite a luz a cada retorno, os Δt são 8, 2, 0,5, 0,125… Cada um é 1/4 do anterior, o fator (1 − v)/(1 + v), que é o quadrado do Doppler. Os ecos se acumulam até a Terra chegar, em t_H = 6,4/0,6 ≈ 10,67 min.

O Doppler relativístico fica fora da ementa. Só entra se sobrar tempo e o professor aceitar, e aqui o fator dá exatamente 2.

O código só trabalha com d = 8 e v = 0,6, que são os valores da apresentação. Antes o núcleo recebia `d` e `v` como parâmetros, e isso saiu para o código ficar mais simples de ler.

Todo número físico sai de `fisica.py`. O `cenas.py` só desenha, e nada de física fica escrito à mão nele.

## Regras das figuras e animações

### Ferramenta e formato

As regras gerais estão no `perfil.md`: Manim CE, 1080p60 em 16:9, transições de 2 a 6 s entre estados estáticos, fundo branco, contraste mínimo das cores e vírgula decimal. Nesta aula valem também estas:

- O PNG de um estado é o último quadro da cena que o produz, e o `manimflow` salva os dois juntos, então o estático e o vídeo nunca divergem.
- A parte Estilo de `cenas.py` define `COR_TEXTO` como cor padrão de `Tex`, `MathTex`, `Text`, `Dot`, `Line`, `DashedLine` e `Arrow`. Qualquer outra classe de mobject precisa de `color=` explícito.

### Layout

- O grupo pediu a imagem centrada, como tela cheia. Se o slide quiser texto ou equação ao lado, ele reduz a imagem. No começo o diagrama ficava encostado à esquerda, e o grupo abandonou esse layout.
- Os dois eixos têm a mesma escala, para a luz sair a 45°.
- A região desenhada é uma `Janela`, da parte Estilo de `cenas.py`, com limites em min-luz e uma escala. O retângulo dela, somado às margens dos rótulos dos eixos, `MARGEM_DIR` e `MARGEM_TOPO`, fica centrado no quadro.
  - `JANELA_T`, usada de S0 a S5, no D e no C: x de −2,2 a 10,5, t de −1,2 a 11,5, 0,58 unidade de tela por min-luz.
  - `JANELA_H`, no fim do R: x de −4,5 a 10,5, t de −2,5 a 11,5, escala 0,525. Ela cresce para a esquerda e para baixo, onde os eixos da Terra abrem.

### Texto dentro do diagrama

- Nenhuma equação. Entram só os rótulos dos eixos, os nomes dos eventos (Emissão, Reflexão, Colisão), as coordenadas nos eventos, "Herói", "Terra (espelho)" e valores pontuais das análises, como 4,8, 6,4, τ = 8, 8 min e 4 min-luz. Os eixos da Terra levam "(min-luz)" no rótulo.
- Rótulos em português e números com vírgula decimal, como 4,8. No MathTex a vírgula precisa ser `{,}`, e a função `num()` já cuida disso.
- As coordenadas vão na cor do referencial, azul para a Terra e laranja para o herói. Quando são iguais nos dois, como na Emissão, aparece uma linha só, na cor do texto.

### Paleta

As cores são as do `perfil.md`, com estes papéis. O contraste da tabela é medido contra o branco.

| Uso | Constante | Cor | Contraste |
|---|---|---|---|
| Fundo | `config.background_color` | `#FFFFFF` | |
| Texto, eventos (pontos e nomes) | `COR_TEXTO`, `COR_EVENTO` | `#1A1A1A` | 17,4 |
| Terra e eixos da Terra | `COR_TERRA` | `#1F6FB2` | 5,3 |
| Referencial do herói (eixos, coordenadas, título) | `COR_HEROI` | `#D9480F` | 4,3 |
| O herói em si (linha de mundo, ponto, nome "Herói", seta de velocidade) | `COR_HEROI_ESCURO` | `#9A3412` | 7,3 |
| Luz (só linhas) | `COR_LUZ` | `#B8860B` | 3,3 |
| Destaques das análises (simultaneidade, contração, hipérbole, radar) | `COR_DESTAQUE` | `#2B8A3E` | 4,4 |

O projeto começou com fundo escuro, `#1E1E1E`. O grupo trocou para branco porque o template dos slides é branco.

### Elementos do diagrama

- As linhas de mundo começam em t = 0, inclusive a da Terra.
- Em qualquer diagrama, a linha de mundo do herói coincide com o eixo ct_H dele. Quando as duas tinham o mesmo laranja, o grupo achou confuso. Agora `linha_heroi()` desenha a linha em `COR_HEROI_ESCURO`, com espessura 7 e um contorno branco de 2 de cada lado, que corta o eixo e as marcas embaixo dela. A regra é tom escuro para o herói e laranja para o referencial dele.
- Os eixos oblíquos são os do herói no diagrama da Terra e os da Terra no `R_RefHeroi`. Eles vão só no sentido positivo e não levam "(min-luz)". Têm uma marca por unidade própria e número só nos pares. Nenhum número fica em cima de um evento, por isso o 8 do eixo ct_H, que cai na Colisão, não aparece.
- Para ler as coordenadas do herói, só os eventos que precisam ganham tracejados de projeção, e hoje é só a Reflexão. A grade oblíqua completa aparece apenas durante a animação dos eixos do herói e some no fim dela.

## Sequência atual

Os estados vão no diagrama da Terra até o R, que termina no referencial do herói. O `plano.yaml` tem a mesma sequência, com a duração e a cena de cada transição.

- **S0, `S0_Base`, estático.** Eixos da Terra, linha da Terra em x = 8 e o herói na origem.
- **S1, `S1_EixosHeroi`, ~4 s.** A grade e os eixos do herói aparecem sobre os da Terra e se fecham de v = 0 até 0,6. Depois a grade some.
- **S2, `S2_Reflexao`, ~4,7 s.** A Emissão entra com um flash e "(0, 0)". O herói e a luz crescem juntos até a Reflexão, em taxa linear e sincronizados em t_T. A Reflexão entra só com a coordenada da Terra, (8, 8) em azul.
- **S2b, `S2b_InstanteReflexao`, ~3,5 s.** Mostra em verde o instante da Reflexão no diagrama da Terra, nesta ordem:
  1. Tracejado horizontal em t_T = 8, da Reflexão até a linha do herói.
  2. Ponto escuro do herói em (4,8; 8), com "6,4" verde logo abaixo e à direita. É o relógio do herói nesse ponto.
  3. Tracejado vertical desse ponto até o eixo x_T, com "4,8" verde na fileira dos números do eixo, entre o 4 e o 6. É a posição do herói, para a Terra, no instante da Reflexão.
  4. Por último, "(4,8, 8)" verde à esquerda do ponto do herói, um pouco acima, porque embaixo passa a linha dele. São as coordenadas desse ponto na Terra.

  A horizontal é o "mesmo instante" para a Terra e liga o 8 ao 6,4. A vertical é o "mesmo lugar" para a Terra. Não confundir com (4,8, 6,4), que mistura referenciais. O 6,4 é o t_H do ponto, e as coordenadas dele no herói são (0, 6,4). Todo o verde some no início do S2c.

  Antes havia duas chaves, uma vertical da Terra, de 0 a 8, e outra ao longo da linha do herói, até 6,4. O grupo trocou as chaves por esses tracejados. Houve também uma versão com a horizontal indo até o eixo ct_T, e o grupo preferiu a vertical até o x_T. Antes disso já tinham saído pares de coordenadas, uma chave vertical do herói e um tracejado em t_H = 4.
- **S2c, `S2c_CoordsHeroi`, ~1,9 s.** Parte do S2b. O verde some, e depois entram os tracejados laranja de projeção da Reflexão até os eixos do herói e a coordenada dele, (4, 4) em laranja.
- **S3, `S3_Colisao`, ~2,6 s.** Parte do S2c, já sem o verde. Entram o raio refletido e o trecho final do herói até a Colisão, que aparece com (6, 10) em azul e (0, 8) em laranja. O estado final tem todas as coordenadas e as projeções, que eram o antigo S4.
- **S5, `S5_Simultaneidade`, ~4 s.** Parte do S3. Uma linha verde com o rótulo "8 min-luz" sai de t_T = 0 e gira até t_H = 0, onde ganha os rótulos t_T = 4,8 e 6,4 min-luz.
- **S3v, `S3_Colisao`, estático.** De volta à imagem do S3, sem vídeo. Existe no plano porque o R parte do S3: depois do slide do S5, o slide seguinte mostra de novo o S3 e o vídeo do R começa dele.
- **R, `R_RefHeroi`, ~4,7 s.** Parte do S3, não do S5. Somem os textos dos eixos, as coordenadas e os rótulos "Herói" e "Terra (espelho)". Um boost de Lorentz contínuo leva ao referencial do herói. Os eixos dele fecham em 90°, os da Terra abrem para fora e a luz fica a 45°. Entram os números e as coordenadas do herói. Por último entram os tracejados verdes da Reflexão até os eixos do herói. O horizontal, em t_H = 4, mostra a simetria entre a ida e a volta da luz, e o vertical, em x_H = 4, marca onde ela acontece. A chave "8 min" e os rótulos do radar saíram porque deixavam a figura confusa.

A classe `Boost` de `cenas.py` redesenha tudo a cada quadro. Ela aplica Lorentz às coordenadas da Terra e recorta o resultado na janela. O parâmetro é a fração da rapidez, atanh v. Os eixos vêm de `Diagrama.eixo(w, tempo, cor, a)`, que interpola entre o estilo do `Axes` em a = 0, com a reta inteira e a ponta na borda, e o oblíquo em a = 1. Durante o boost a janela também vai de `JANELA_T` para `JANELA_H`, e o diagrama se desloca e encolhe um pouco, para os eixos da Terra terminarem compridos.

O estado inicial do R é o quadro dinâmico em a = 0 com os textos do S3 por cima. Não dá para começar com `E.s3()`, porque um `FadeOut` só nos números do `Axes` faz a cena trocar o `Axes` pelos filhos dele, e a linha do eixo some junto.

O grupo pediu os eixos do herói antes dos eventos. Por enquanto, o "referencial do herói" que aparece primeiro são os eixos oblíquos dentro do diagrama da Terra, e não o diagrama `R_RefHeroi`. Falta confirmar com o grupo que o pedido era esse.

### Estáticos extras

- **`C_Contexto`.** Imagem de contexto que vem antes dos diagramas de Minkowski. Só tem o eixo x, sem tempo, em dois painéis empilhados que mostram onde cada um está no instante da Emissão. O painel de cima é o referencial da Terra em t_T = 0, com o herói em x_T = 0 indo a 0,6c para a direita, o espelho parado em x_T = 8 e a cota verde "8 min-luz". O de baixo é o referencial do herói em t_H = 0, com o herói parado em x_H = 0, a Terra vindo a 0,6c para a esquerda a partir de x_H = 6,4 e a cota "6,4 min-luz". O espelho é a barra escura, e o planeta é o círculo azul logo atrás dela. O eixo usa a mesma janela e a mesma escala de x dos diagramas, então o x_T fica alinhado com o do `S0_Base`. Os dois painéis ficam centrados na vertical.
- **`R_RefHeroi`.** Hoje é o último quadro da animação R. É o diagrama no referencial do herói, com os eixos dele ortogonais. A luz sai a 45° e a Terra se aproxima, numa linha que começa em x_H = 6,4 no instante t_H = 0 e vai até encontrar o herói. Dois tracejados verdes ligam a Reflexão aos eixos do herói, por baixo das linhas e do ponto. O de t_H = 4 mostra a simetria da luz, e o de x_H = 4 marca onde a reflexão acontece. O grupo pediu para tirar a chave "8 min" e os rótulos "8 min" e "4 min-luz", que poluíam a figura. Os números do radar ficam no texto do slide. Também a pedido do grupo, os eixos da Terra aparecem oblíquos e abertos para fora, recortados na janela maior, `JANELA_H`. O ct_T sobe para a esquerda até t_H ≈ 7, com marcas até 5, e o x_T desce para a direita, com marcas até 2. Por causa deles, "Emissão" fica embaixo e à esquerda da origem, e "Herói" fica à esquerda dos números do eixo ct_H, em t_H = 5.
- **`D_Dilatacao`.** Diagrama da Terra com os eixos do herói e a hipérbole c²t² − x² = 64, ou seja, τ = 8 min. Ela vai de t_T = 8 no eixo da Terra até a Colisão. A Colisão leva o rótulo t_T = 10 e t_H = 8.

### Ecos

A ideia é do grupo. No referencial do herói, ele "se cumprimenta" cada vez mais rápido até chegar ao espelho.

- **`G_TempoEco`, estático.** Gráfico de Δt_H, a ida e volta em min, contra a distância da Terra na emissão, x_H em min-luz. Os dois eixos têm a mesma escala e ficam na cor do texto, porque o gráfico não é um diagrama de Minkowski e não há referencial para colorir. Uma reta verde sobe de (0; 0) até (6,4; 8). Com a Terra encostada a ida e volta é instantânea, e o tempo cresce com a distância, Δt = 1,25·x. A equação vai no slide. Pontos pretos marcam os ecos sucessivos, (6,4; 8), (1,6; 2), (0,4; 0,5)…, que se acumulam perto de zero. Os dois primeiros têm tracejados e valores verdes, 8 e 2 no eixo Δt e 6,4 e 1,6 no eixo x. Os eixos têm só marcas, sem números.

  A primeira versão já era esta, igual ao esboço do quadro. A segunda usou no eixo x "quanto a Terra já se aproximou", com uma reta descendo de 8 a 0. O grupo voltou para a reta crescente, que é mesmo Δt em função da distância.
- **`G_TempoEcoT`, estático.** O mesmo gráfico, para comparar com o `G_TempoEco`, com o instante t_H da emissão, em min, no eixo x. A reta Δt = 8 − 0,75·t vai de (0; 8) até a chegada, em t_H ≈ 10,67. Os ecos ficam em t = 0, 8, 10, 10,5… Os valores verdes são 8 e 2 no eixo Δt e 8 e 10,67 no eixo t. O código é uma subclasse do `G_TempoEco` que só troca `eixo_x`. O grupo ainda vai escolher um dos dois.
- **`E0_Ecos` → `E_Ecos`, ~5,6 s.** Diagrama do herói, sem os eixos da Terra, na `JANELA_E`, com x de −3,4 a 8, t de −1 a 12 e escala 0,56. Começa com os eixos do herói, a linha da Terra indo de (6,4; 0) até o herói em t_H ≈ 10,67, e o herói e a Emissão na origem. A transição avança t_H em ritmo constante, 0,42 s por minuto. A linha do herói sobe, a luz vai em zigue-zague até a Terra e volta, cada retorno ganha um ponto e o herói reemite na hora. À esquerda do eixo ct_H, cotas verdes, que são linhas com traços nas pontas, crescem como cronômetros nas três primeiras idas e voltas. Os valores "8 min", "2 min" e "0,5 min" entram no fim, junto com o ponto e o rótulo "Chegada". São 7 ecos, mas do 5º em diante o zigue-zague já não aparece. A classe `Ecos` monta tudo a partir de `lista_ecos(n)`, e `quadro(T)` desenha o estado em t_H = T.
- **`R_RefHeroi` → `R_Ecos`, ~4,6 s.** Alternativa ao `E0_Ecos` → `E_Ecos`, que continua de onde o `R_RefHeroi` termina. São quatro passos:
  1. Somem os eixos da Terra, os tracejados verdes, os nomes e as coordenadas dos eventos, o ponto da Reflexão, os números e rótulos dos eixos e o "Herói". O ponto da Colisão encolhe até o tamanho de um retorno.
  2. O diagrama passa de `JANELA_H` para `JANELA_E`, redesenhando só as linhas.
  3. Entram os números e rótulos dos eixos, o "Herói" na origem e a primeira cota, já completa e com "8 min".
  4. Os ecos continuam a partir da Colisão, em t_H = 8, no ritmo do `E_Ecos`. No fim entram "2 min", "0,5 min" e a Chegada.

  O último quadro é igual ao do `E_Ecos`.

## Código

```
perfil.md       preferências do professor para todas as aulas, um nível acima desta pasta
CONTEXTO.md     este arquivo
plano.yaml      os estados e as transições, na ordem dos slides
fisica.py       física sem classes: V, DIST, GAMMA, lorentz, lorentz_inv, os eventos, os resultados das análises e equacoes()
test_fisica.py  confere os valores de equacoes() e que os eventos escritos à mão batem com a física
cenas.py        Estilo (cores, fontes, Janela, num, par, linha_heroi), Diagrama (Diagrama, Estados, Boost, Ecos) e as cenas
saida/          renderizações do manimflow: png/ e mp4/, e previa/ para as prévias
```

### Como `cenas.py` funciona

- `Diagrama(obs, jan)` monta os eixos e tem um método por elemento, como `linha_terra`, `heroi_ida`, `luz_volta`, `rotulo_evento`, `eixos_heroi(v)`, `grade_heroi(v)`, `projecoes_heroi` e `linha_simultaneidade(s)`. O `obs`, `"T"` ou `"H"`, diz qual referencial é ortogonal. Os eventos ficam escritos à mão em `fisica.py`, em coordenadas da Terra, e o `test_fisica.py` confere que batem com a física. Os métodos recebem o nome do evento, e as coordenadas do herói saem de `lorentz()`. Nada de classes de física: o repositório vai para o professor, que quer ler o Manim sem atravessar infraestrutura.
- `Estados` cria cada mobject uma vez só e expõe `s0()`, `s1()`, `s2()`, `s2b()`, `s2c()` e `s3()` como listas ordenadas. **A ordem da lista é a ordem das camadas.** O `s2b()` insere os auxiliares verdes no índice 4, logo depois dos eixos do herói e atrás das linhas de mundo, e o `s2c()` põe as projeções no mesmo índice. Se a estrutura de `s1()` mudar, revise esse índice. O S4 não existe mais, porque o grupo pediu que as coordenadas do herói entrem junto com cada evento.
- `rotulo_evento` sempre monta o grupo completo, com nome, coordenadas da Terra e coordenadas do herói, mesmo quando o estado mostra só parte dele. Assim as coordenadas que entram depois não empurram o que já está na tela.

### Regras para escrever ou alterar uma transição

1. Comece com `self.add(*E.sN())`, o estado anterior, e termine exatamente em `E.sN+1()`.
2. Em animações com `ValueTracker` e `always_redraw`, remova o objeto dinâmico no fim, adicione o estático equivalente e chame `self.add(*E.sN+1())` para reordenar as camadas.
3. Herói e luz que crescem juntos usam `rate_func=linear` e segmentos que cobrem o mesmo intervalo de t. Assim, a cada quadro, a ponta dos dois está no mesmo instante.
   - Use um `Create` por `DashedLine`, no padrão, que desenha traço a traço. Com `lag_ratio=0` todos os traços crescem juntos e a linha surge pontilhada de uma vez.
   - A linha do herói é um grupo de contorno branco e linha, então anime com `Create(..., lag_ratio=0)`. No padrão, o Manim desenha o contorno inteiro primeiro, e ele apaga o eixo ct_H à frente do herói.
4. Depois de mexer, renderize e confira a continuidade como explica a próxima seção.
5. Se renomear uma cena, atualize o `plano.yaml`, o docstring do topo de `cenas.py` e este arquivo, e apague os arquivos antigos de `saida/`. Depois rode `manimflow plan validate`.

## Fluxo de trabalho

Na pasta da aula:

```bash
python -m pytest test_fisica.py                # confere a física
manimflow plan validate .                      # confere o plano
manimflow preview . S1_EixosHeroi              # prévia rápida em baixa qualidade, em saida/previa/
manimflow render . D_Dilatacao                 # 1080p60, em saida/png/ e saida/mp4/
```

Para conferir a continuidade, extraia o primeiro e o último quadro de cada MP4 com ffmpeg e compare com os PNGs vizinhos:

```bash
ffmpeg -loglevel error -y -i saida/mp4/X.mp4 -frames:v 1 primeiro.png
ffmpeg -loglevel error -y -sseof -0.05 -i saida/mp4/X.mp4 -update 1 -frames:v 1 ultimo.png
```

A comparação usa numpy e conta a fração de pixels com diferença maior que 60 em algum canal. Até agora ficou sempre abaixo de 0,1%, que é só a compressão do vídeo.

O projeto começou no Manim 0.21 e foi conferido no Manim CE 0.22, que vem com o ManimFlow.

## Pendências e ideias

- O `C_Contexto` já mostra 6,4 min-luz no referencial do herói, o que antecipa a contração. Se o grupo quiser guardar esse resultado para depois, dá para tirar a cota do painel de baixo.
- Confirmar com o grupo a leitura da nova ordem, com os eixos oblíquos primeiro e não o `R_RefHeroi`.
- Ajustar o visual, como tamanhos de fonte, ritmo das transições e texto dos rótulos. O rótulo "Colisão" está perto da borda de cima do quadro.
- Ideias de animação que ficaram de fora e podem voltar se sobrar tempo:
  - cenário físico em 1D sincronizado com o diagrama, em tela dividida;
  - hipérbole do invariante animada;
  - régua de contração e radar animados.

  O boost de Lorentz animado também estava nesta lista e virou o `R_RefHeroi`.
- Doppler como extra opcional.
- A paleta da seção de regras pode virar a base das cores do template dos slides.
