# Perfil do professor

Preferências que valem para todas as aulas. Cada aula pode acrescentar regras no próprio `CONTEXTO.md`, mas não deve contrariar estas sem combinar antes.

## Formato

- Tudo sai do Manim Community (CE), tanto as imagens estáticas quanto os vídeos.
- Saída final em 1080p60, 16:9. PNG para os estados, MP4 para as transições.
- As animações apoiam a fala e nada mais. A apresentação tem que funcionar só com as imagens estáticas, e as animações são transições curtas, de 2 a 6 s, entre elas. Nada de vídeo explicativo no estilo 3Blue1Brown. O contexto e as equações ficam nos slides.
- O último quadro de uma transição é idêntico à imagem do estado seguinte e ao primeiro quadro da transição seguinte.
- No PowerPoint, o slide mostra o PNG e o vídeo fica no mesmo lugar, com "Iniciar: ao clicar" e sem repetição.

## Fundo e cores

- O fundo é branco puro, `#FFFFFF`, porque o slide é branco.
- Toda cor precisa ter contraste de pelo menos 4,3:1 contra o branco em texto e linhas finas, e de 3:1 em linhas grossas. Isso exclui branco, amarelo puro e tons pastel.
- O Manim desenha em branco por padrão, e branco some no fundo. Defina a cor do texto como cor padrão de `Tex`, `MathTex`, `Text`, `Dot`, `Line`, `DashedLine` e `Arrow`, e passe `color=` explícito em qualquer outra classe.

Paleta. O contraste foi medido contra o branco.

| Cor | Hex | Contraste | Uso sugerido |
|---|---|---|---|
| Quase preto | `#1A1A1A` | 17,4 | texto, pontos e nomes de eventos |
| Azul | `#1F6FB2` | 5,3 | primeiro referencial ou objeto principal |
| Laranja | `#D9480F` | 4,3 | segundo referencial |
| Laranja escuro | `#9A3412` | 7,3 | o objeto do segundo referencial em si |
| Dourado | `#B8860B` | 3,3 | luz, só em linhas grossas |
| Verde | `#2B8A3E` | 4,4 | destaques das análises |

## Texto

- Rótulos em português.
- Números com vírgula decimal, como 4,8. No `MathTex` a vírgula precisa ser `{,}`, senão o LaTeX põe um espaço depois dela.
- Imagem centrada, pensada como tela cheia. Se o slide quiser texto ao lado, ele reduz a imagem.
