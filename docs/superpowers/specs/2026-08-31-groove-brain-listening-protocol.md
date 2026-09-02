# Groove Brain — protocolo de escuta cega, pré-registrado

- **Status:** pré-registrado em 2026-09-01, **não executado**. Depende da decisão O1.
- **Projeto:** `ableton-mcp-server`
- **Documento de origem:** [design canônico de dataset e treinamento](2026-08-31-groove-brain-dataset-training-design.md), seção 18.5
- **Instrumento:** `lab/scripts/make_listening_set.py`

Este documento é escrito **antes** de qualquer coleta. Alterá-lo depois de ver
resultado anula o teste.

## 1. O que está sendo comparado

O **Transformer HVO mascarado** treinado no plano 6, checkpoint `m1-seed0`,
contra o **retrieval** sobre o split de treino — o incumbente, que é o que sai no
produto se nada vencer.

`[fato]` A avaliação automática do plano 5 já mediu um empate entre os dois no F1
de hit em infill (`0,5045` contra `0,5005`, margem 22× menor que o ruído) e uma
derrota do modelo em distribuição por lane (`1,204` contra `0,041` do amostrador
marginal). O teste de escuta existe porque F1 não é a pergunta do produto, e
porque a §23 exige avaliação cega antes de qualquer promoção. A expectativa,
registrada aqui para poder ser contrariada, é que o modelo perca.

## 2. Tarefas

30 trials, congelados, gerados uma vez com seed `20260831` a partir do split de
validação, distribuídos pelas quatro tarefas da família de infill que têm verdade
de referência mais as duas de geração:

| Tarefa | Trials |
|---|---|
| `temporal_infill` | 6 |
| `lane_infill` | 6 |
| `fill` | 5 |
| `continuation` | 5 |
| `variation` | 4 |
| `free_generation` | 4 |

A distribuição real sai do sorteio do `build_cases` com o seed registrado e é
gravada em `key.json`; a tabela acima é o alvo, não uma imposição sobre o
sorteio.

## 3. Apresentação

- Cada trial são dois arquivos MIDI, `trial-NN-A.mid` e `trial-NN-B.mid`.
- A ordem de A e B é sorteada por trial com o seed `20260831`, registrado.
- Ambos passam pelo mesmo exportador, mesmo kit General MIDI, mesmo teto de
  velocity, mesmo BPM de 120.
- Nenhum nome de sistema aparece em nome de arquivo, pasta ou metadado.
- O `key.json`, que diz qual letra foi qual sistema, é gravado **fora** da pasta
  que o avaliador abre.
- O avaliador não vê este documento antes de terminar.

## 4. O que o avaliador responde

Por trial:

1. **Qual dos dois você usaria?** A, B, ou nenhum dos dois. "Nenhum" conta como
   empate e sai do denominador.
2. Quatro notas de 1 a 5, para **groove**, **utilidade**, **controle** e
   **novidade**.

## 5. Limiar de promoção

`[decisão]` Promoção exige que o limite inferior do intervalo de Wilson a 95%
para a preferência pelo challenger fique acima de 50%. Com 30 comparações
pareadas e empates fora do denominador, isso é **≥ 21 de 30**: 21 dá limite
inferior ≈ `0,521`; 20 dá ≈ `0,488` e reprova.

Esse número está aqui antes da coleta e não é renegociado depois.

## 6. Quantos avaliadores — decisão O1, aberta

`[risco]` Com **um** avaliador, o intervalo de confiança é sobre **tarefas**, não
sobre pessoas. O resultado é uma decisão legítima do proprietário sobre o próprio
produto e **não generaliza para outros músicos**. Se for esse o caso, o model
card precisa dizer exatamente isso, nessas palavras.

Com mais de um avaliador, a unidade de análise passa a ser o avaliador e o
tamanho de amostra precisa ser recalculado antes de coletar.

A coleta não começa enquanto essa decisão não estiver escrita.

## 7. Regra de parada

- O conjunto é gerado **uma vez**, a partir do seed registrado.
- Cada avaliador vê cada trial **uma vez**.
- O teste **não** é repetido com o mesmo conjunto depois de ver o resultado. Uma
  nova rodada exige nova geração formal de dataset ou de modelo, conforme a §17,
  rung M4.
- Nenhum limiar deste documento muda depois da coleta.

## 8. O que este teste não decide

Ele decide o gate G6, promoção. Não decide arquitetura: GrooVAE e o decoder
event-based não estão neste comparativo e são planos próprios. E não substitui a
avaliação automática — um modelo que passe aqui e reprove em anti-cópia ou em
validade estrutural continua reprovado.
