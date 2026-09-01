# Groove Brain — especificação canônica de dataset e treinamento neural

- **Status:** reescrita em 2026-08-31 após auditoria adversarial do commit-base `721e77b`, com medição direta do corpus, do código e das fontes primárias.
- **Execução autorizada por este documento:** os nove planos da seção 21.
- **Natureza do trabalho:** experimento pessoal do proprietário. O corpus, o dataset, os modelos e os artefatos ficam nesta máquina. Nada é vendido, publicado ou distribuído.
- **Projeto:** `ableton-mcp-server`
- **Escopo:** bateria e ritmo MIDI. Nenhum Composer Brain, nenhum lançamento, nenhuma publicação.
- **Documento de produto relacionado:** [Groove Brain Extension](2026-08-30-groove-brain-extension-design.md)

## 0. Como ler este documento

Toda afirmação relevante carrega uma classificação. Ela existe para impedir que uma hipótese vire premissa por repetição.

| Marca | Significado |
|---|---|
| `[fato]` | verificado nesta máquina, no repositório ou em fonte primária, com o comando ou caminho registrado |
| `[decisão]` | escolha de produto ou de engenharia, revogável, mas não sujeita a debate durante a execução |
| `[hipótese]` | acreditamos que sim, ainda não medimos |
| `[experimento]` | existe um teste desenhado que resolve isso |
| `[risco]` | pode dar errado de um jeito que custa caro |

Números sem marca são resultado de medição registrada na seção 4.

## 1. Decisão em uma frase

Groove Brain é um gerador de bateria local e offline para o Ableton Live: um corpus privado de MIDI de bateria passa por canonicalização lossless, remapeamento de articulações, deduplicação em camadas e splits por família; três arquiteturas neurais competem sob orçamento idêntico contra um baseline determinístico que já funciona; o vencedor só existe se ganhar em escuta cega, originalidade e custo de CPU; e o modelo roda num helper nativo isolado, atrás da Extension, com escrita explícita e readback verificado.

O produto é útil mesmo se nenhum modelo vencer. Essa é a característica de projeto, não o plano B.

## 2. Decisões abertas do proprietário

Duas perguntas não podem ser respondidas por análise. Nenhuma delas impede começar; cada uma trava um gate específico, mais adiante.

### O1 — quem avalia no teste cego `[trava o gate G5]`

Um avaliador ou vários. Com um só, o intervalo de confiança é sobre tarefas, não sobre pessoas, e o model card não pode afirmar que outros músicos preferem o modelo. Para um experimento pessoal, um avaliador é escolha legítima. Precisa ser declarada antes de coletar, não depois de ver o resultado.

### O2 — teto de tamanho da `.ablx` `[trava o plano 8]`

Quantos MiB é aceitável instalar. O número precisa existir antes de escolher runtime ONNX e quantização, porque ele elimina opções. Referência medida: o `.ablx` do Gate 0 tem `154.852` bytes. O documento de produto sugere pacote core abaixo de 500 MiB.

## 3. Precedência entre documentos

Esta especificação é a fonte de verdade para **dados e treinamento neural do Groove Brain**. Ela substitui, somente nesse domínio:

- as seções 13.4–13.6, 14, 16 e 17 de `2026-08-30-groove-brain-extension-design.md`, isto é, pipeline de preparação, labels, split, representação musical, modelo neural e anti-memorização;
- as decisões gerais de Music Brain sobre Composer Brain, REMI+ e composição multitrack.

Continuam valendo, sem alteração, duas seções desse mesmo documento de produto: a 13.3 (corpus bruto fora do Git) e a 15 (busca e referência). Referências a "seção N" fora deste parágrafo apontam para este documento.

Continuam válidas as decisões de produto `[decisão]`:

- bateria e ritmo somente;
- operação local e offline;
- uma única instalação `.ablx` para o produto final;
- UI web servida localmente;
- Extension como única camada autorizada a tocar o Live;
- candidatos antes de escrita;
- aplicação explícita, revalidação e readback;
- modelo e inferência fora da thread e do host do Ableton.

## 4. Estado verificado do corpus

### 4.1 Inventário `[fato]`

Fonte: `%LOCALAPPDATA%\AbletonMCPServer\groove-build-v2\ingestion-report.json` e `catalog_v2.sqlite`; `groove-build-v1/corpus-report.json`.

| Medida | Valor |
|---|---|
| Arquivos descobertos e processados | `183.429` |
| MIDIs válidos | `180.614` |
| Falhas de parser | `2.815`, todas com o mesmo reason code `groove_midi_error` |
| Repetições por digest bruto | `11.296` |
| Arquivos únicos por bytes | `169.318` |
| Bytes de MIDI | `99.933.371` |
| Note events | `11.403.162` |
| Eventos totais | `23.737.765` |
| Coleções distintas | `280` |

O seed de retrieval teve duas gerações: V1 com `2.048` representantes, V2 no `HEAD` com `1.685`. Existe uma experiência local não commitada que troca o seed por `500` itens; ela não é baseline nem dataset. O baseline é o `HEAD`.

### 4.2 Auditoria medida

Números apurados sobre o catálogo completo e sobre amostras aleatórias de arquivos únicos por bytes, seed `20260831`. O plano 2 reproduz tudo isso como código versionado.

**Estrutura musical**

| Medida | Valor | Escopo |
|---|---|---|
| Compasso 4/4 | `155.844` (86,3%) | catálogo |
| Outros compassos | `24.770` (13,7%): 6/8 `10.002`, 3/4 `5.995`, 7/8 `1.853`, 5/4 `1.646`, 2/4 `1.106`, 12/8 `1.095` | catálogo |
| Comprimento | 1 barra `59.795`, 2 barras `52.671`, 8 barras `34.703`, 4 barras `27.604` | catálogo |
| Arquivos com menos de 2 barras | `56.842` de `169.318` (33,6%) | únicos |
| Janelas de 2 barras sem sobreposição | `354.749` | únicos |
| Papéis presentes por arquivo | mediana `4`, p90 `7`, máximo `14` | catálogo |
| Hits por barra | mediana `16`, p10 `9`, p90 `25`, máximo `129` | catálogo |
| Tempo meta presente no SMF | 97,8% | amostra 1.000 |

**Expressão**

| Medida | Valor | Escopo |
|---|---|---|
| `offset_std` mediano | `9,76` ticks canônicos (PPQ 480) ≈ 10,2 ms a 120 BPM | catálogo |
| `offset_std` p90 / p99 | `26,6` / `33,8` ticks | catálogo |
| Arquivos com `offset_std` ≥ 10 ms a 120 BPM | 74,5% | catálogo |
| Arquivos perfeitamente quantizados | 1,3% | catálogo |
| `velocity_std` mediano | `0,196` normalizado (≈25 unidades MIDI) | catálogo |
| `velocity_std` p10 / p90 | `0,074` / `0,289` | catálogo |

**Perda por grade densa**

| Grade | Notas fundidas | Arquivos afetados |
|---|---|---|
| 16 avos (32 passos / 2 barras) | 3,51% | 36,6% |
| 32 avos (64 passos) | 1,38% | 18,9% |
| 64 avos (128 passos) | 0,92% | 13,0% |

Distribuição de células com múltiplas notas na grade de 16 avos: `2` notas em `6.853` células, `3` em `522`, `4` em `151`, `5` em `30`, e cauda até `8`.

**Repetição e vazamento**

| Medida | Valor | Escopo |
|---|---|---|
| Padrões de onset de 2 barras únicos | 82,4% (`34.351` de `41.697` janelas) | amostra 20.000 |
| Janelas em padrão repetido | 26,0% | amostra 20.000 |
| Padrões repetidos que aparecem em coleções diferentes | 9,9% (`346` padrões) | amostra 20.000 |
| Esqueletos kick+snare cruzando coleções | `1.030` | amostra 20.000 |
| Esqueletos kick+snare únicos | 63,0% | amostra 20.000 |

**Cobertura de labels**

| Eixo | Cobertura |
|---|---|
| `feel`, `density`, `microtiming`, `kit`, `collection`, `license` | 100% |
| `section` | `151.678` (84,0%) — `variation` 101.372, `groove` 45.146, `fill` 39.956 |
| `style` | `103.265` (57,2%) — `straight` 66.907, `swing` 26.269 |
| `genre`, `subgenre`, `bpm` | **não existem** na taxonomia |
| Coleções eletrônicas/hip-hop somadas | `8.167` (4,5%); estritamente eletrônicas ≈`3.174` (1,8%) |

### 4.3 Mapeamento de articulações — o defeito que bloqueia a representação

Este é o achado com maior efeito sobre o desenho, e não estava registrado em nenhum documento anterior.

`[fato]` A ontologia atual mapeia apenas as alturas de percussão General MIDI, 35 a 81 (`groove_intelligence/drum_roles.py`). Tudo fora disso vira `other_percussion`. Medido em amostra de 6.000 arquivos únicos, `361.264` notas:

| Papel | Massa de notas |
|---|---|
| `other_percussion` | **24,34%** |
| `kick` | 24,15% |
| `snare` | 23,88% |
| `ride` | 8,83% |
| `tom_low` | 3,35% |
| `hat_closed` | **3,06%** |
| `crash` | 2,77% |
| `hat_pedal` | 2,07% |
| `hat_open` | 0,85% |
| demais 9 papéis | somados 6,9% |

`63,6%` das notas em `other_percussion` estão **fora** da faixa GM 35–81. As alturas mais frequentes ali são `22`, `21`, `26`, `25`, `24` — a faixa que as bibliotecas Toontrack usam para articulações de chimbal — e `60`, `61`, `62`, `63`, que essas bibliotecas usam para articulações de pratos.

A conclusão é direta: **o chimbal, que é a lane que carrega a subdivisão rítmica, está sendo jogado no balde genérico.** Somadas, as três lanes de chimbal recebem 5,98% da massa de notas, o que é implausível para loops de bateria. Realocando só as cinco alturas acima, o chimbal passaria a ≈17%, que é o valor esperado.

A distorção não é uniforme. Por coleção, a fração de notas em `other_percussion`:

| Coleção | Fração |
|---|---|
| `EZX_LATIN_PERCUSSION` | 80,4% |
| `EZD_POP#ROCK` | 43,7% |
| `WEST_COAST_ROCK_GROOVES` | 40,5% |
| `SUPERIOR_DRUMMER_3` | 38,6% |
| `THE_JAZZ_SESSIONS` | 36,8% |
| `EZDRUMMER_3` | 36,0% |

`[risco]` Treinar um HVO por lane sobre esse mapeamento ensina uma estrutura falsa: `other_percussion` vira a segunda lane mais densa e mistura chimbal, articulação de prato e percussão latina. Nenhum controle de densidade por lane, nenhuma lane bloqueada e nenhuma métrica de F1 por lane significa o que diz.

`[decisão]` Um **mapa de articulações por coleção** é pré-requisito do dataset, não refinamento. Ele entra no plano 2 e produz:

1. histograma de alturas por coleção, com massa de notas e coocorrência temporal;
2. mapa `coleção → altura → papel canônico`, versionado e auditado à mão;
3. métrica de cobertura: fração de massa de notas resolvida para um papel específico, por coleção;
4. gate: uma coleção com mais de 10% da massa em `other_percussion` depois do remapeamento fica fora do treino da V1 e volta para o retrieval.

O proprietário tem as bibliotecas instaladas e pode exportar os mapas MIDI oficiais de cada uma; isso torna a auditoria muito mais barata que inferir por estatística.

`[decisão]` A ontologia V1 continua com os 18 papéis. Percussão latina não ganha lanes novas na V1: coleções dominadas por ela saem do treino em vez de inflar a ontologia.

#### Resultado do plano 2, executado em 2026-08-31

`[fato]` A medição foi refeita sobre o catálogo inteiro — 278 coleções, `10.671.574` notas nos arquivos únicos por bytes — gravando, por coleção e por altura, um perfil rítmico: notas por arquivo, espaçamento entre onsets, fração em posições de colcheia e concentração no fim do compasso. Os papéis foram atribuídos comparando cada altura da banda com as lanes GM presentes no próprio corpus (42 fechado, 44 pedal, 46 aberto), não por intuição.

O que a evidência sustentou e o que não sustentou:

- **21 → `hat_pedal`**, estável: distância `0,061` do GM 44 contra `0,213` do segundo colocado, e 73% das 120 coleções que usam a altura chegam ao mesmo resultado sozinhas;
- **22, 24, 25, 26, 27 → `hat_closed`**, com ressalva declarada: são inequivocamente da família chimbal — a coocorrência no mesmo tick entre elas é de `0,035%`, ou seja, articulações mutuamente exclusivas do mesmo instrumento — mas a articulação exata **não** é determinável, porque a concordância entre coleções fica em 20% a 50%. O colapso na lane de subdivisão é registrado como perda documentada e reversível;
- **60–63 permanecem sem resolução.** Carregam 7,9% da massa do corpus, enquanto o crash GM 49 mede 3,0 notas por arquivo e gap mediano de 8 passos; e em `EZX_LATIN_PERCUSSION` só 60 e 61 existem, com 62 e 63 zerados, que é o par de bongô do GM. A mesma altura é instrumento diferente em bibliotecas diferentes, e nenhuma leitura global se sustenta.

#### Camada do fabricante, que substituiu a inferência onde existe

`[fato]` O Superior Drummer 3 instala uma base SQLite por biblioteca em `%PROGRAMDATA%\Toontrack\Superior Drummer 3\Database\<coleção>\midiDB`. São **190 bases, 186 legíveis**. Cada uma traz, por arquivo de groove: as peças de bateria tocadas (`KITPIECES` + `REL_ENT_KITS`), o gênero (`GENRE`), tags de execução (`TAGS`), nome descritivo com andamento (`HEADER`), `Tempo`, compasso, resolução e intensidade.

O join é exato: `LIBRARY.Name` é a coleção do corpus e o caminho é o mesmo trocando `_EZD2MIDI_` por `Drums Groove MIDI/`. **109.554 arquivos rotulados, 103.096 casados com o corpus.**

`[decisão]` A altura recebe a peça que **100% dos arquivos que a contêm** declaram; entre as peças que valem para todos, vence a mais rara, porque é a afirmação mais específica que o dado sustenta. Peça que não nomeia um papel único — `Toms` cobre três lanes, `Special` e `Brushes` não nomeiam instrumento — não atribui nada.

`[decisão]` O override só é aplicado onde o GM deixa a altura em `other_percussion`. Onde os dois discordam numa altura que o GM já resolve, o vocabulário do fabricante costuma ser o mais grosso — uma peça `Ride` cobrindo o sino, uma `Crash` cobrindo splash e china — e aplicar perderia detalhe. Esses casos ficam registrados em `scripts/vendor_labels_report.md` em vez de virarem mudança.

`[fato]` 60–63 ficaram resolvidos, e cada biblioteca deu uma resposta diferente: no `SUPERIOR_DRUMMER_3` são chimbal (60 aberto, 61 e 62 fechado); no `EZX_LATIN_PERCUSSION`, 60 e 61 são o par de bongô. Nunca foram crash. Isso confirma na prática por que o mapa precisa ser por coleção.

`[fato]` Efeito medido, com a camada do fabricante por cima da inferência rítmica: chimbal sobe de `5,67%` para **`21,95%`** da massa de notas; `other_percussion` cai de `24,34%` para **`6,48%`**; nenhum papel já resolvido pelo GM é rebaixado. O mapa cobre 229 coleções, 168 delas com entrada do fabricante e 1.000 overrides de altura.

`[fato]` Gate G1 no estado atual: **66 de 278 coleções ficam fora do treino**, contra 144 antes da camada do fabricante.

`[fato]` A base também entrega os eixos que a seção 13 registra como inexistentes na taxonomia: **gênero** (`Pop/Rock/Country` 57.670, `Metal` 21.672, `Latin` 10.014, `Jazz` 4.206, `Funk` 3.485, `Blues` 2.800, `Soul` 2.278, `Electronic` 2.036) e **andamento** por arquivo. O plano 4 consome esses rótulos em vez de inferir gênero por nome de pasta.

Artefatos no repositório: `scripts/measurement.py`, `scripts/build_articulation_map.py`, `scripts/build_vendor_labels.py`, `scripts/report.py`, `scripts/measurement_output.json`, `scripts/measurement_report.md`, `scripts/vendor_labels_report.md` e `ableton_mcp_server/groove_intelligence/articulation_map.json`. Os rótulos por arquivo ficam fora do Git, em `%LOCALAPPDATA%\AbletonMCPServer\groove-vendor-labels\vendor_labels.jsonl`. A projeção de treino é `groove.hvo.v3`; `groove.hvo.v2` fica intacta e continua alimentando o retrieval, com teste de regressão por digest.

### 4.4 Origem do corpus

`[fato]` O corpus vem de `C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi` (`scripts/ingest_private_corpus.py:18`) e é composto por MIDI das bibliotecas de bateria que o proprietário tem instaladas. As `280` coleções carregam o nome do produto de origem. As maiores: `ezx_drumkit_from_hell` (19.756), `ezd_pop_rock` (8.550), `ezx_latin_percussion` (6.786), `real_blues` (4.657), `zildjian_artists` (4.270), `groove_monkee_progressive` (3.868), `ezdrummer_3` (2.879), `brooks_wackerman_grooves` (1.811), `platinum_samples` (1.614).

`[decisão]` Este é um experimento pessoal. O corpus, o dataset, os checkpoints e o modelo ficam nesta máquina. Nada é vendido, publicado nem distribuído. Não há gate de direitos, nem marcação de redistribuição, nem quarentena por item.

A proveniência continua sendo registrada, e não por causa de licença: `source_id`, digest e coleção de origem são **insumo técnico** do pipeline. Sem eles não há dedupe por bytes, não há mapa de articulações por coleção, não há cluster de família e não há split sem vazamento. A seção 12 depende disso inteira.

`[fato]` Nota de estado, não restrição: a tabela `payloads` do seed guarda MIDI bruto comprimido — um artefato descomprime para os 242 bytes exatos de um arquivo do catálogo, com SHA-256 igual. Esse seed está em `resources/groove_seed/index.sqlite` desde `aa680c7` e também dentro da wheel `ableton_mcp_server-0.6.0-py3-none-any.whl`. Fica registrado porque é diferente do resto do programa, que é local por construção.

## 5. Estado verificado do software

### 5.1 O que existe e serve `[fato]`

- parser e serializer SMF com limites explícitos;
- envelope MIDI lossless;
- ontologia de 18 papéis de bateria;
- projeções `groove.hvo.v2`, `groove.features.v2` e `groove.grammar.v2`;
- inventário reiniciável, hashes, proveniência e manifests;
- taxonomia de collection, style, section, feel, density, microtiming e kit;
- SQLite imutável para retrieval, com busca, evidence, comparação e similaridade;
- geração determinística, transformações e recombinação multi-parent;
- mapping tardio e aplicação guardada no Live;
- protocolo de provider neural, subprocesso isolado, limites de processo e fallback;
- harness de gates de **runtime**: `gates.py` publica limiares, `lab.py` executa seis gates nomeados (`contract`, `fallback`, `reproducibility`, `quality`, `privacy_license`, `cost_latency`), `promotion.py` assina a decisão;
- Gate 0 `.ablx` com helper nativo e write/readback observado no Ableton: `status=ok`, `code=READBACK_MATCH`, 4 notas intencionadas e 4 lidas de volta, hashes iguais, `durationMs=42,77`, receipt persistido, zero processo helper órfão.

### 5.2 O que existe e **não** serve para treino `[fato]`

- `groove.hvo.v2` funde eventos silenciosamente: `derive_hvo` agrupa por `(papel, barra, passo)` e grava `hit=1` com média de velocity e offset (`groove_intelligence/projections.py:85-108`). Serve retrieval, não serve como alvo de treino;
- o mapeamento de papéis perde 24,3% da massa de notas em `other_percussion` (seção 4.3);
- o `NeuralSubprocessProvider` é uma fronteira de segurança, não uma IA treinada;
- o código antigo de `music_brain` e o branch `wip/music-brain` são heurísticos e ficam só como baseline ou descarte seletivo.

### 5.3 O que não existe

Dataset tensorial de treino; mapa de articulações por coleção; cluster de near-duplicates e registro de splits; loader de treino; arquitetura PyTorch; loss, optimizer, scheduler ou checkpoint; harness de comparação **entre arquiteturas**; modelo treinado; export ONNX validado; inferência neural dentro do `.ablx`; dashboard final.

## 6. O que torna esta extensão diferente

Não é tamanho de modelo. Um gerador de bateria com 5M de parâmetros não compete com serviço de nuvem em capacidade bruta, e não precisa. O que torna esta extensão única é um conjunto de garantias que quase nenhum gerador musical oferece, e todas elas já estão provadas no repositório ou são consequência direta do desenho.

1. **Nada sai da máquina.** Sem conta, sem upload, sem telemetria. Os dois bridges são loopback e isso é verificado por teste (`tests/test_extension_loopback.py`). `[fato]`
2. **Nunca sobrescreve nada em silêncio.** Candidato antes de escrita, aplicação explícita, revalidação e readback com hash. O Gate 0 já demonstrou o ciclo completo dentro do Live. `[fato]`
3. **Lanes bloqueadas são respeitadas por construção.** A máscara é entrada do modelo, não filtro depois da geração. Um chimbal que você travou não é regenerado e depois descartado; ele nunca é predito. `[decisão]`
4. **Toda saída tem procedência.** Cada candidato aponta para artefatos-pai com digest, e o `groove_evidence` mostra de onde veio. Nenhum resultado é uma caixa preta sem lastro. `[fato]`
5. **O produto funciona sem o modelo.** Retrieval e transformações determinísticas são o caminho principal enquanto o neural não vencer, e continuam sendo o fallback depois. Falha do provider degrada, não quebra. `[fato]`
6. **Nada de MIDI é perdido.** O envelope lossless preserva o arquivo original; a grade é uma projeção, não a verdade. Isso é o que permite prometer round-trip exato. `[decisão]`
7. **Anti-cópia é gate, não relatório.** Um candidato que reproduz um item do treino é rejeitado e contabilizado, com limiar congelado antes do experimento. `[decisão]`
8. **Instalação única.** Um `.ablx`, sem Python, sem CUDA, sem runtime externo para o usuário. `[decisão]`

O critério de qualidade decorre disso: a extensão é boa quando um baterista programador abre o painel, pede um groove, entende de onde ele veio, trava o que gostou, regenera o resto, e o clipe no Live é exatamente o que a UI mostrou. Nenhuma dessas coisas depende de o modelo ser grande.

## 7. Objetivo mensurável da V1 e não objetivos

O primeiro modelo deve gerar e editar grooves curtos de bateria que:

1. respeitem as condições aprovadas pelo gate de cobertura da seção 13: no mínimo BPM, compasso, seção e função, densidade global e por lane, energia, complexidade, swing e lanes bloqueadas;
2. façam geração livre, variação, fill, infill temporal, infill de lanes e continuação curta;
3. preservem velocity e microtiming, que o corpus comprovadamente tem (seção 4.2);
4. usem um clipe do Ableton como referência com força controlável;
5. retornem vários candidatos reprodutíveis por seed;
6. não copiem um item nem uma família do treino;
7. rodem dentro dos sete limites de processo da seção 19.4, com destaque para `cpu_seconds <= 2,0`;
8. vençam o melhor baseline em avaliação cega.

**Não objetivos:** melodia, baixo, harmonia, arranjo; áudio generativo; canções completas; LLM como gerador central; inferência online; treinamento na máquina do usuário final; substituir o Ableton como editor; escalar parâmetros antes de provar dados, controles e avaliação; lanes novas para percussão latina na V1.

## 8. Abordagens comparadas

### 8.1 A — Transformer HVO condicional e mascarado `[challenger recomendado]`

Entrada densa por tempo e papel; heads separados predizem hit, multiplicidade, velocity e offset. Máscaras representam exatamente locks, lanes e regiões. Decoding iterativo dá geração, infill e variação com o mesmo backbone.

**Vantagens:** controles diretos; paralelização; alinhamento com o HVO existente; preservação explícita de lanes; export simples.

**Riscos:** células densas escondem rolls e flams — medido em 3,51% da massa de notas em 16 avos e 0,92% em 64 avos, o que torna o canal de multiplicidade obrigatório; cada passo de decoding consome do teto de `cpu_seconds <= 2,0`; probabilidades de hit podem colapsar para o padrão médio.

### 8.2 B — decoder autoregressivo event-based `[challenger obrigatório]`

Eventos carregam posição ou delta, lane, velocity, offset e duração. O modelo prediz a sequência sob condições e grammar mask.

**Vantagens:** representa múltiplos hits, rolls e durações sem fundi-los; continuidade temporal natural.

**Riscos:** inferência sequencial mais cara, o que colide de frente com o orçamento de CPU; locks e infill exigem ordenação cuidadosa; invalidade estrutural pode crescer.

### 8.3 C — GrooVAE/HVO `[baseline neural obrigatório]`

Baseline da família GrooVAE, separando score de expressão e reconstruindo hit, velocity e microtiming por espaço latente.

**Vantagens:** referência reproduzível; interpolação e humanização bem estudadas; custo pequeno.

**Riscos:** reconstrução e amostragem disputam o mesmo espaço; controle fino por região e lane é menos direto.

`[fato]` O repositório `magenta/magenta` está arquivado desde 2026-01-06 e é somente leitura. Serve como referência de arquitetura e configuração, nunca como dependência instalável. A reimplementação é em PyTorch.

### 8.4 Regra de decisão `[decisão]`

Não há votação por training loss. A mesma divisão de dados, as mesmas tarefas, o mesmo orçamento de passos, as mesmas seeds e o mesmo protocolo humano comparam A, B e C. O Transformer HVO recebe prioridade de engenharia porque encaixa melhor no produto, e pode perder.

Se nenhum neural vencer retrieval mais transformações determinísticas, o produto continua determinístico e o treino para. Isso não é fracasso: é o resultado que o desenho previu.

Diffusion e modelo de texto ficam fora do primeiro bake-off. Ampliam complexidade sem resolver deficiência demonstrada pelos três candidatos.

## 9. Arquitetura do programa

```text
corpus MIDI privado (read-only)
            |
            v
 inventário + manifest de origem (source_id, digest, coleção)
            |
            v
 parser SMF -> IR lossless -> mapa de articulações por coleção -> ontologia de lanes
            |
            +--> fingerprints + dedupe exato / canônico / rítmico
            |                         |
            |                         v
            |                 clusters de família
            |                         |
            v                         v
 janelas + condições --------> train / validation / blind test
            |
            +--> HVO dense shards (hit, subhits, velocity, offset, máscaras)
            +--> event shards
            +--> envelope lossless referenciado
                              |
                              v
          baselines determinísticos / GrooVAE / AR / masked HVO
                              |
                              v
       métricas + nearest-neighbor + avaliação cega + model card
                              |
                         gate de promoção
                              |
                              v
                   export ONNX + equivalência + orçamento de CPU
                              |
                              v
              provider local isolado -> candidates -> verifier
                              |
                        aprovação humana
                              |
                              v
                 Extension write + readback no Live
```

`[decisão]` Treinamento e produto têm dependências separadas. PyTorch, CUDA, notebooks e ferramentas de análise nunca entram no runtime do usuário.

## 10. Contratos de dados

### 10.1 `SourceRecord`

Registro imutável por arquivo:

- `source_id` estável, não derivado de caminho público;
- hash bruto e tamanho;
- caminho relativo apenas no catálogo privado;
- versões de parser, normalizer, mapa de articulações e taxonomia;
- status e reason code;
- coleção de origem e mapa de articulações aplicado;
- família inferida e confiança.

Nomes de marca podem ser usados localmente para interpretar hierarquia e mapping, e não aparecem em pesos, cards públicos ou nomes de produto.

### 10.2 `CanonicalGroove`

- envelope MIDI lossless;
- tempo, compasso, PPQ e comprimento musical;
- eventos normalizados, altura original preservada e papel canônico resolvido;
- projeção HVO com multiplicidade;
- sequência event-based;
- features e labels com confiança;
- hashes bruto, canônico, rítmico e de expressão;
- `family_cluster_id` e `split_id`;
- flags de qualidade, colisão, truncamento, expressão e cobertura de mapeamento.

`[decisão]` O modelo nunca abre `.mid` diretamente. Consome uma projeção versionada do `CanonicalGroove`.

### 10.3 `DatasetManifest`

- seleção exata de fontes e digests;
- versões de parser, normalizer, mapa de articulações, ontologia, fingerprint e tokenizer;
- regras de janela, grade e subeventos;
- **fração de massa de notas não representável pela grade escolhida**, comparada ao orçamento declarado;
- **fração de massa de notas resolvida para papel específico**, por coleção;
- algoritmo e thresholds de clustering, mais a distribuição de tamanho de componente;
- seed e algoritmo do split;
- contagens por split, coleção, seção, compasso, BPM, lane e família;
- descarte por reason code;
- digests dos shards;
- data, ambiente e comando reproduzível.

`[decisão]` Dataset, shards, envelopes e checkpoints ficam fora do Git, no workspace externo da seção 16.4. O repositório recebe schemas, código, fixtures sintéticas e relatórios. O motivo é de higiene de repositório e tamanho, não de licença: um `index.sqlite` de 27 MB dentro de um pacote Python já mostrou o custo.

## 11. Canonicalização musical

### 11.1 Ontologia e articulações

Os 18 papéis: kick, snare, rim, clap, hat closed, hat open, hat pedal, tom low, tom mid, tom high, crash, splash, china, ride, ride bell, tambourine, cowbell, other percussion.

`[decisão]` A altura de origem é preservada no envelope. O modelo aprende papel canônico, resolvido pelo mapa de articulações da coleção (seção 4.3). O mapping para Drum Rack ou SD3 acontece depois da geração.

### 11.2 Grade e microtiming

`[fato]` Nenhuma grade densa de uma nota por célula representa o corpus sem perda. Fundindo por `(papel, barra, passo)`: 3,51% da massa de notas em 16 avos, 1,38% em 32 avos, 0,92% em 64 avos. Aumentar a grade reduz e não elimina, porque flams e rolls ficam sistematicamente abaixo de qualquer célula praticável.

`[decisão]` Consequências obrigatórias:

- o tensor HVO de treino carrega um canal explícito de multiplicidade: `subhits` inteiro por célula e `collision_flag` derivado, mais a referência ao envelope. O round-trip do alvo de treino é exato, e a perda é atribuída à política, nunca ao silêncio;
- a política de versão do dataset declara por número quanto da massa de notas cada representação descarta, e o `DatasetManifest` publica esse número;
- baseline: duas barras em 4/4, 32 passos de semicolcheia, offset contínuo, com canal de multiplicidade;
- `[experimento]` challenger de 64 passos, com prior medido de queda de 3,51% para 1,38%.

`[decisão]` Outros compassos ficam preservados no IR e são avaliados separadamente. 4/4 cobre 86,3% do corpus; 6/8, com `10.002` arquivos, é o único candidato realista a segundo compasso na V1. O resto permanece no retrieval e é explicitamente fora de distribuição para geração neural.

### 11.3 Tensores

Shards HVO, separados:

- `hit`: uint8 `[example, time, lane]`;
- `subhits`: uint8 `[example, time, lane]`, contagem real de eventos na célula;
- `velocity`: float normalizado, com loss mask por hit;
- `offset`: deslocamento normalizado pela célula, com loss mask por hit;
- `observed_mask`: posições fornecidas ao modelo;
- `target_mask`: posições cobradas pela tarefa;
- condições categóricas e contínuas;
- IDs opacos de exemplo, família e origem.

Shards event-based guardam tokens e atributos equivalentes e apontam para o mesmo exemplo canônico.

`[decisão]` Formato físico sharded e content-addressed, arrays NumPy mmap-friendly, índice JSONL canônico. Nenhum pickle é aceito.

Ordem de grandeza: 32 passos × 18 lanes = 576 células por exemplo; ≈6,2 KiB por exemplo com float32 para velocity e offset. Com `354.749` janelas sem sobreposição são ≈2,2 GB, e ≈4,4 GB com hop de uma barra.

### 11.4 Janela

`[decisão]` Unidade primária: duas barras. Arquivos maiores geram janelas com sobreposição somente depois de o split por família estar definido. Janelas do mesmo arquivo ou família nunca atravessam splits. Fills usam uma barra de contexto mais região-alvo final; continuação curta usa contexto anterior explícito.

`33,6%` dos arquivos únicos têm menos de duas barras. Política explícita: um arquivo de uma barra vira janela de duas barras por repetição, marcada com `looped=true`, ou fica como janela de uma barra com o resto em `observed_mask=0` e `target_mask=0`. `[experimento]` A escolha entre as duas é ablação do plano 4, e o manifest registra qual foi usada. Repetir a barra sem marcar a flag é proibido: cria periodicidade artificial de duas barras que o modelo aprenderia como estrutura.

## 12. Dedupe, famílias e splits

### 12.1 Camadas

1. bytes idênticos;
2. eventos equivalentes após remover metadados irrelevantes;
3. equivalência rítmica por lanes, ignorando mapping de altura;
4. near-duplicate por distância HVO, grammar e features;
5. família por hierarquia, lineage do gerador anterior e assinaturas de geração.

`[decisão]` `family_cluster_id` é o fecho transitivo sobre a união das arestas das camadas 1, 2, 3 e 5. A camada 4 **não** cria aresta de cluster por padrão: single-linkage sobre distância contínua colapsa em componente gigante e torna o split impossível. Ela entra como filtro de amostragem e métrica publicada.

`[experimento]` Se o plano 4 quiser promover a camada 4 a aresta, publica antes a distribuição de tamanho de componente e prova que o maior fica abaixo de 5% dos exemplos. Acima disso, o clustering é rejeitado e o threshold reduzido.

`[fato]` A camada 5 sozinha vaza. Em amostra de 20.000, `346` padrões de onset de 2 barras repetidos (9,9% dos repetidos) e `1.030` esqueletos de kick e snare aparecem em coleções diferentes. Agrupar só por diretório deixaria essas cópias em lados opostos do split.

Thresholds de near-duplicate são calibrados com pares exatos, variações conhecidas e pares musicais diferentes, e congelados antes de abrir o blind test.

### 12.2 Falta de lineage

Se prompt, template, batch ou seed do gerador original existirem, ficam apenas no catálogo privado. Se não existirem, o sistema combina origem e hierarquia, hash canônico, fingerprint de hits por lane, assinatura de velocity e offset, comprimento, BPM, seção, taxonomia e clustering conservador.

`[decisão]` A ausência de lineage não bloqueia experimento, reduz a força da alegação de generalização e aparece no model card.

### 12.3 Split

Ordem obrigatória:

1. construir clusters sem olhar métricas do modelo;
2. reservar blind test por cluster e família;
3. dividir o restante em train e validation;
4. estratificar aproximadamente por coleção, seção, BPM, compasso e cobertura de lanes, sem quebrar clusters;
5. congelar IDs e digests;
6. treinar normalizadores, embeddings e qualquer vocabulário somente no train;
7. impedir que o retriever consulte validation ou test durante avaliação neural.

Alvo: aproximadamente 80/10/10 por exemplos, subordinado a clusters inteiros.

Duas verificações obrigatórias:

1. o relatório publica a distribuição de tamanho de cluster, o maior componente em percentual de exemplos e o desvio real do alvo alcançável. Se o maior componente impedir o alvo, reduz-se o threshold e reagrupa; nunca se quebra um cluster;
2. um teste de vazamento por conteúdo, independente do clustering, compara hashes exato, canônico e rítmico de todo o blind test contra todo o train e validation. Qualquer coincidência é falha de build.

## 13. Labels e condições

### 13.1 Cobertura real

Nomes de diretório dão sinal de style, section e feel, e não verdade absoluta. Cada label carrega origem e confiança. Aliases passam pela taxonomia; categoria rara ou ambígua vira `unknown` em vez de rótulo inventado.

`[fato]` Cobertura atual: `section` 84,0%, `style` 57,2%, `feel`/`density`/`microtiming`/`kit`/`collection` 100%, `genre` e `subgenre` inexistentes, `bpm` inexistente.

`[decisão]` BPM vem do evento meta de tempo do SMF, presente em 97,8% dos arquivos, e não do nome do diretório. Extrair BPM do caminho é contaminado: o prefixo numérico de coleção (`210@GROOVE_MONKEE_*`, `200241@REAL_BLUES`) é indistinguível de um token de andamento e produz `210` como valor mais frequente.

`[decisão]` Gênero e subgênero exigem um mapa explícito `collection → genre`, construído e auditado à mão sobre as 280 coleções, no plano 2. Enquanto ele não existir e não for medido, gênero e subgênero não são condição do modelo.

`[decisão]` Techno e dark techno saem da lista de prioridade de auditoria. As coleções eletrônicas somam `8.167` arquivos (4,5%), as estritamente eletrônicas ≈`3.174` (1,8%), e a interseção literal de techno com dark é da ordem de uma centena. O corpus é de bateria acústica de rock, metal, blues, jazz, latin e pop, e a extensão deve ser honesta sobre isso.

A auditoria manual mede a precisão do que importa: `fill` contra `groove` e `variation`, as seções nomeadas, o `style`, e a cobertura do mapa de articulações.

### 13.2 Condições do modelo

- estilo; gênero e subgênero somente depois do mapa auditado;
- BPM normalizado, lido do SMF;
- compasso;
- beat, fill e seção;
- densidade global e por lane;
- energia;
- complexidade;
- swing e feel;
- comprimento;
- lanes e regiões bloqueadas;
- força de mutação;
- embedding opcional de referência.

`[decisão]` Condition dropout ensina modo parcial e totalmente não condicionado. Controles contínuos são avaliados por resposta monotônica, não apenas por classificação. O dashboard só oferece condição cujo train split tenha cobertura e qualidade mínimas.

### 13.3 Texto livre

"Rock pesado 140 BPM com fill no fim" passa por parser local determinístico e produz uma `GrooveSpec` visível. Sinônimos multilíngues mapeiam para taxonomia e controles. Nenhum LLM é necessário.

`[decisão]` Termo sem cobertura falha de forma visível. Um pedido de "techno sombrio" mostra o termo como não coberto e oferece o mais próximo com aviso, em vez de devolver um groove de rock rotulado como techno. Cobertura ausente é erro de cobertura, não pedido inválido.

`[decisão]` Modelo de linguagem local pequeno só poderá competir futuramente pela tradução de texto. Nunca produz notas nem escreve no Live.

## 14. Tarefas de treinamento

Uma task sampler versionada cria exemplos sem mudar o split:

1. **free generation:** todas as células-alvo mascaradas;
2. **variation:** parte observada, parte corrompida ou mascarada;
3. **temporal infill:** região temporal contínua removida;
4. **lane infill:** uma ou mais lanes removidas;
5. **fill:** região final condicionada por seção e função;
6. **continuation:** bloco seguinte condicionado pelo anterior;
7. **humanize:** hits quantizados e velocity simplificada para a expressão original;
8. **reference:** padrão-alvo condicionado por embedding do clipe de referência e força de similaridade.

`[decisão]` `reference` só usa pares sustentados por família ou style, ou corrupção controlada. Não cria pares aleatórios e chama isso de aprendizagem.

`[fato]` `humanize` tem base: `offset_std` mediano de 9,76 ticks canônicos (≈10,2 ms a 120 BPM), 74,5% dos arquivos acima de 10 ms, apenas 1,3% perfeitamente quantizados, `velocity_std` mediano de 0,196.

`[decisão]` Condição obrigatória antes de promover a tarefa: `offset_std` agregado confunde swing e feel sistemáticos com jitter de performance. O plano 2 decompõe o offset em viés médio por `(papel, posição na grade)` e resíduo, e `humanize` só é promovido se o **resíduo** tiver variedade útil. Sem essa decomposição, um corpus perfeitamente swingado e perfeitamente rígido passaria no teste.

`[fato]` O Groove MIDI Dataset (1.150 arquivos, 13,6 h, performance humana capturada, CC BY 4.0) serve como benchmark auxiliar separado para calibrar essa decomposição. Não é misturado ao corpus principal.

`[hipótese]` A distribuição inicial de tarefas fica registrada em config, nunca como constante escondida. Ablations comparam task mix e removem tarefas que degradem o núcleo.

## 15. Modelos e orçamento

### 15.1 Masked HVO

- embeddings de lane, posição, tarefa e condições;
- Transformer encoder bidirecional;
- heads de hit, multiplicidade, velocity e offset;
- BCE ou focal loss para hit conforme desbalanceamento;
- Smooth L1 para velocity e offset somente onde há hit;
- regularização de densidade e controle somente se ablation provar benefício;
- decoding iterativo de confiança, com temperatura e threshold por lane.

| Nível | Configuração | Parâmetros do encoder | Função |
|---|---|---|---|
| smoke | 2 camadas, `d_model=128`, 4 heads | ≈0,4M | provar pipeline e overfit |
| small | 6 camadas, `d_model=256`, 8 heads, FFN 1024 | ≈4,7M | challenger principal inicial |
| medium | 8–10 camadas, `d_model=512`, FFN 2048 | ≈25M–31M | somente se a curva de escala justificar |

O alvo antigo de 20–50M descreve a faixa medium e nem chega ao topo dela. A contagem real é calculada e registrada.

`[risco]` `354.749` janelas × 576 células são ≈2,0·10⁸ células por época, das quais só ≈6% estão ocupadas — a mediana é 16 hits por barra. O sinal efetivo é da ordem de 1,1·10⁷ hits por época. Um modelo de 25M parâmetros sobre esse volume é candidato natural a memorizar, o que faz da seção 18.4 um gate e não um relatório.

`[decisão]` Modelo maior não avança se small já saturar dados ou qualidade.

### 15.2 Event-based AR

Decoder-only pequeno, embeddings fatorados de tempo, lane, velocity e offset, causal mask e grammar mask. Mesmo orçamento de parâmetros e passos do masked small. Avalia especialmente rolls, flams, continuidade e validade.

`[risco]` É o candidato com maior chance de ganhar em qualidade e perder no orçamento de CPU. O spike do plano 3 mede isso antes de treinar.

### 15.3 GrooVAE

Implementação reproduzível em PyTorch da tarefa de duas barras. Config, conversão e métricas seguem a publicação original onde aplicável. Pesos publicados servem como referência; o comparativo principal treina no mesmo split permitido.

## 16. Ambiente e reprodutibilidade

### 16.1 Separação `[decisão]`

- preparação e inventário: Windows ou Linux, usando os contratos existentes;
- treinamento: ambiente Linux reproduzível;
- produto: Windows x64, helper nativo e ONNX Runtime sem Python;
- dados e checkpoints: workspace externo ao Git;
- manifests, fixtures e relatórios sanitizados: repositório.

### 16.2 GPU local

`[fato]` Verificado em 2026-08-31 nesta máquina: `NVIDIA GeForce RTX 5070`, `12227 MiB` de VRAM, driver `610.74`, compute capability `12.0` (Blackwell), CUDA UMD `13.3`, 64 GB de RAM, i9-12900KS.

Suficiente para smoke, small, ablations e, no porte de modelo desta especificação, para o treino completo com mixed precision, gradient accumulation e activation checkpointing. VRAM não é a restrição: small com ≈4,7M e medium com ≈25M cabem com folga.

`[fato]` A partir do PyTorch 2.12 a wheel CUDA 12.8 está descontinuada, a wheel padrão é CUDA 13.0, CUDA 13.2 é experimental, e a orientação para GPUs Blackwell é usar wheels CUDA 13.0+, com driver mínimo `580.65.06` no Linux e `580.88` no Windows. O driver instalado satisfaz o piso.

`[decisão]` A implementação não copia números deste texto. Executa um environment probe, registra driver, GPU e compute capability, instala versões pinadas em lock e congela a matriz que passar smoke, checkpoint resume e determinismo declarado.

### 16.3 Determinismo

Cada run registra commit e digest de dirty-state; digests de dataset, split e config; versões de Python, PyTorch, CUDA, cuDNN e drivers; GPU, precisão e kernels; seeds de Python, NumPy, PyTorch e data workers; estado de sampler, optimizer e scheduler; checkpoints e métricas.

`[decisão]` Determinismo bit a bit entre GPUs não é prometido. Reprodutibilidade significa configuração e lineage completos, curvas compatíveis e saída exata apenas dentro da matriz declarada.

### 16.4 Disco e retenção

`[fato]` Verificado em 2026-08-31: `C:` com `193 GB` livres de 1,9 TB (90% em uso), `D:` com `386 GB` livres de 5,5 TB, `F:` com `458 GB` livres de 1,9 TB.

Pela estimativa da seção 11.3, o dataset denso completo fica entre 2 e 5 GB, e um checkpoint de small ou medium com estados de optimizer fica abaixo de 1 GB. **Disco não é o gargalo deste programa.**

`[decisão]` Política:

- workspace de treino em `D:` ou `F:`, nunca em `C:`;
- manter o raw read-only;
- manter uma build de dataset promovida e uma candidata;
- por run, manter `best`, `last` e checkpoints de marco;
- apagar cache regenerável somente por comando explícito com caminho verificado;
- nunca usar o repositório, a home ou a raiz como alvo de limpeza;
- a projeção 1%/10%/100% continua obrigatória como prova de que o pipeline mede antes de escrever.

## 17. Escada de execução

| Degrau | O que faz | Bloqueado por |
|---|---|---|
| **E0** environment probe | GPU, mixed precision, forward/backward, save e resume, DataLoader multiprocess, export de grafo mínimo | — |
| **D0** auditoria de corpus | reproduz a seção 4.2 como código; constrói o mapa de articulações e o mapa `collection → genre`; decompõe swing e jitter; mede clusters e duplicação cruzada sobre o corpus inteiro | — |
| **P0** spike de CPU e ONNX | **feito em 2026-08-31.** Resultado: 32 passos de decoding com tokenização passo-por-token a `0,375` CPU-segundo, contra 16 passos com célula-por-token; `intra_op_num_threads=1` é obrigatório porque mais threads pioram o orçamento. Ver seção 19.4 | — |
| **D1** build de 1% | duas builds idênticas, digests, splits, round-trip exato, ausência de vazamento, disco e throughput | D0 |
| **M0** overfit controlado | smoke em 32–256 exemplos até memorizar de propósito. Incapacidade de overfit é bug, não falta de escala | D1 |
| **M1** tiny 1% | deterministic/retrieval, GrooVAE, event AR e masked HVO sob orçamento curto. Geração válida, controle, ausência de colapso | M0, P0 |
| **D2/M2** 10% e bake-off | congela representação, grades, thresholds e protocolo. No mínimo três seeds por candidato. Seleção por validation e avaliação humana, sem tocar no blind test | M1 |
| **D3/M3** full run | dataset 100%, treino da configuração vencedora e de uma baseline forte. O blind test abre uma vez, para a decisão registrada | M2 |
| **M4** controle e hard examples | ajusta task mix e controles com train e validation. Novo blind test só com nova geração formal de dataset e modelo | M3 |
| **R0** runtime optimization | FP32/FP16 quando aplicável e INT8 dinâmico para CPU. Quantização só passa com equivalência musical e qualidade | M3, G6 |

`[decisão]` R0 confirma, não descobre. O número que decide a arquitetura sai de P0, antes de M1. Se R0 contradisser P0, o erro está em P0 e a arquitetura é revista, não o limite.

## 18. Avaliação

### 18.1 Integridade

- parse e serialize válidos;
- 100% das saídas dentro dos limites de altura, lane, tempo e comprimento;
- zero violação de lanes e regiões bloqueadas;
- zero família ou near-duplicate conhecida cruzando splits;
- nenhuma consulta do retriever ao blind test;
- **zero evento perdido sem registro**, definido como critério duplo: o round-trip `CanonicalGroove → tensor de treino → CanonicalGroove` é exato para 100% dos exemplos, com `subhits` e envelope; e a fração de notas não representável pela grade é medida, publicada no manifest e menor ou igual ao orçamento declarado antes do build.

### 18.2 Predição

Precision, recall e F1 de hit por lane; MAE ou Smooth L1 de velocity condicionado a hit; MAE de offset condicionado a hit; acerto de multiplicidade em células com colisão; fill e infill por região e lane; calibração da probabilidade de hit; reconstrução e amostragem medidas separadamente para o VAE.

`[decisão]` F1 por lane só é reportado sobre lanes cuja massa de notas foi resolvida pelo mapa de articulações. Reportar F1 de `other_percussion` como se fosse um instrumento é ruído.

### 18.3 Musicalidade e controle

Aderência a densidade, energia, swing, complexidade e referência; resposta monotônica dos controles contínuos; distribuição por lane e posição; diversidade intra-lote e entre seeds; silêncio, repetição e colapso; validade de rolls e flams; distância e cobertura em relação ao corpus.

### 18.4 Originalidade

Cada candidato é comparado ao train por hash canônico, fingerprint HVO com invariâncias declaradas, grammar e features, sequência event-based, família e origem, e cópia de trechos contíguos.

`[decisão]` O limiar varia por tarefa: uma variação pode ser próxima da referência; free generation não pode reproduzir uma família inteira. Resultado acima do limiar é rejeitado, regenerado e contabilizado.

`[decisão]` Os limiares são congelados antes do primeiro bake-off e registrados com digest, com uma referência que impede leitura complacente: no próprio corpus, 26,0% das janelas de 2 barras repetem exatamente o padrão de onset de outra janela. Um gerador que copiasse nessa mesma taxa seria indistinguível do corpus por essa métrica. O gate exige que a taxa de coincidência exata **contra o train** fique abaixo da coincidência interna do corpus, não apenas "baixa".

### 18.5 Teste humano

Protocolo pré-registrado:

- pelo menos 30 tarefas representativas;
- prompts e controles congelados;
- candidatos anonimizados, volume e kit normalizados;
- comparação do neural contra o melhor retrieval ou transformação determinística;
- avaliação de groove, utilidade, controle, novidade e vontade de usar;
- ordem aleatória e identidade do sistema oculta;
- número de avaliadores (**O1**), unidade de análise e tratamento de empates declarados antes de coletar;
- intervalo de confiança publicado.

`[decisão]` Promoção exige limite inferior do intervalo acima de 50%. Com 30 comparações pareadas e empates fora do denominador, isso é **≥21 de 30** vitórias: o limite inferior de Wilson a 95% dá ≈0,521 para 21, e ≈0,488 para 20, que falha. O número é registrado antes da coleta e não é renegociado depois.

`[decisão]` Limitação declarada: com um único avaliador o intervalo é sobre tarefas, não sobre pessoas, e o resultado não generaliza. É aceitável como decisão do proprietário e precisa aparecer no model card com essas palavras.

Se não houver preferência, deterministic e retrieval permanecem como produto principal.

## 19. Runtime e `.ablx`

### 19.1 Export

`[decisão]` PyTorch exporta um grafo ONNX com inputs, outputs e dynamic axes mínimos, pela rota `torch.export` e exportador baseado em Dynamo. TorchScript está descontinuado desde o PyTorch 2.10; o exportador legado baseado em trace não é rota suportada.

Uma suíte dourada compara logits, decoding e groove canônico entre PyTorch e ONNX, com tolerância numérica declarada por saída. Diferença além da tolerância bloqueia o artefato.

`[decisão]` O decoding iterativo é parte do contrato de equivalência. Se o laço viver fora do grafo, a suíte compara a sequência completa de passos, não só os logits do primeiro.

### 19.2 Provider

O helper recebe somente `ConditionCard`, referência canônica limitada, seed e limites. Não recebe caminho de corpus, comando, shell, token externo nem objeto do Live. A saída passa por parser, verifier, anti-cópia e mapping antes de virar candidato.

`[fato]` Os limites de processo são aplicados por Job Object no Windows e por process group no POSIX (`groove_intelligence/resource_limits.py`).

### 19.3 Execution providers

CPU é o baseline universal. ONNX Runtime permite providers ordenados com fallback; aceleração GPU é opcional e só entra se estiver empacotada e compatível com instalação única. CUDA na máquina de desenvolvimento não vira requisito do usuário.

`[fato]` O repositório `microsoft/DirectML` declara estado de manutenção, e a Microsoft direciona desenvolvimento novo para Windows ML, que expõe as mesmas APIs do ONNX Runtime e seleciona o execution provider conforme o hardware. A página de execution providers do ONNX Runtime lista DirectML como provider de produção sem marca de depreciação e não menciona Windows ML; as duas fontes precisam ser lidas juntas.

`[risco]` Windows ML resolve e provisiona execution providers pelo sistema operacional, o que conflita com operação offline e instalação única. `[experimento]` Se o spike mostrar que o provider precisa ser baixado sob demanda, Windows ML sai do caminho da V1 e o produto fica em CPU pura.

### 19.4 Orçamento

`[fato]` Os limites não são metas de P95: são tetos rígidos por chamada, declarados em `ProviderLimitsV1` (`groove_intelligence/provider.py:49-59`) com `le=` no schema, portanto não elevam por configuração.

| Limite | Valor | Efeito no modelo |
|---|---|---|
| `generation_seconds` | `<=5,0` | teto de parede por chamada |
| `cpu_seconds` | `<=2,0` | **teto de tempo de CPU somado entre threads**; com 8 threads são 0,25 s de parede |
| `startup_seconds` | `<=2,0` | carga da sessão ONNX e dos pesos precisa caber aqui |
| `shutdown_seconds` | `<=1,0` | encerramento limpo do helper |
| `memory_mib` | `<=512` | modelo, runtime e arena de execução |
| `max_response_bytes` | `<=262.144` | candidato serializado em JSON |
| `max_events` | `<=2.048` | eventos por candidato |

`cpu_seconds <= 2,0` é o limite que decide a viabilidade. Um decoding iterativo de N passos multiplica o custo por N. O plano 3 orça passos × threads dentro de 2 s de CPU, ou o contrato é formalmente renegociado antes de projetar o decoding.

#### Resultado do spike do plano 3, medido em 2026-08-31

`[fato]` Dois modelos não treinados de tier small, exportados para ONNX pelo exportador Dynamo do PyTorch 2.12 e medidos sob ONNX Runtime 1.23.2 em CPU. Cada configuração rodou três vezes e é julgada pelo **pior** resultado de CPU, porque uma medição isolada perto do teto não é estável: a primeira varredura colocou `cell_token` em 32 passos e a rerodada imediata em 16.

| Tokenização | Sequência | Parâmetros | ONNX | Passos máximos em 1 / 4 / 8 threads |
|---|---|---|---|---|
| célula por token | 576 | `4.758.791` | `419.850` B | **16 / 16 / 8** |
| passo por token | 32 | `4.802.174` | `415.564` B | **32 / 32 / 32** |

`[fato]` Custo por passe: `cell_token` gasta `0,061` CPU-segundo por passe em 1 thread, linear no número de passos. `step_token` gasta cerca de `0,003`, **20× menos**, e a 32 passos com 8 threads ainda fica em `0,375` CPU-segundo — cinco vezes abaixo do teto.

`[fato]` Achado estrutural, não previsto: **mais threads pioram o orçamento**. Como `cpu_seconds` soma o tempo entre threads, `cell_token` a 32 passos custa `2,016` CPU-segundos em 1 thread e `4,406` em 8. O provider deve fixar `intra_op_num_threads=1`; paralelizar reduz o tempo de parede e estoura justamente o limite que vale.

`[decisão]` A tokenização levada ao plano 6 é **passo por token**, com as lanes dobradas na dimensão de canal. Cabe com folga em qualquer configuração de thread, enquanto célula-por-token fica a um fator de 2 do teto e depende de o usuário não ter a CPU ocupada. O decoding do produto é orçado em **32 passos**, e esse número entra no plano 6 como restrição de arquitetura, não como meta.

`[risco]` O que o spike **não** decidiu: se 32 tokens são musicalmente expressivos o bastante. Dobrar 18 lanes num único vetor por passo força a estrutura de lane pelo canal, e isso é pergunta do bake-off do plano 6, não de uma medição de custo. Se `step_token` perder em qualidade, `cell_token` continua viável a 16 passos com uma thread.

`[risco]` A memória medida, 420 a 442 MiB contra o teto de 512, está contaminada: o processo de laboratório carrega PyTorch ao lado do ONNX Runtime, e o helper do produto é nativo e nunca carrega PyTorch. É limite superior de harness, não leitura do provider. Antes de afirmar que o teto de memória está apertado, é preciso medir num processo sem PyTorch.

`[fato]` Footprint: as bibliotecas nativas do ONNX Runtime somam `33,4 MiB` e os pesos de qualquer variante ficam abaixo de `420 KB`. Somados ao piso de `154.852` bytes do Gate 0, runtime e modelo ocupam por volta de 34 MiB, bem abaixo dos 500 MiB sugeridos pelo documento de produto. Insumo direto para a decisão **O2**.

Artefatos: `lab/` com ambiente CPU-only isolado em `.venv-lab`, `lab/scripts/run_spike.py`, `lab/artifacts/budget.json` e o relatório em `docs/superpowers/plans/2026-08-31-groove-brain-cpu-onnx-budget-spike-result.md`.

Demais itens:

- alvo de produto: candidato warm em aproximadamente `<=1 s` no hardware do autor;
- `[fato]` baseline medido de pacote: o `.ablx` do Gate 0 tem `154.852` bytes, com helper nativo de `258.048` bytes descomprimido. Runtime ONNX e pesos entram acima desse piso;
- teto numérico de tamanho da `.ablx` declarado antes de escolher runtime e quantização (**O2**);
- cold start, tamanho do modelo e tamanho total medidos antes da promoção;
- nenhuma meta é relaxada depois de ver o blind test.

## 20. Gates binários

Um gate só é binário se outra pessoa puder avaliá-lo sem consultar a intenção do autor.

| Gate | Passa quando | Falha significa |
|---|---|---|
| **G0** Ambiente | GPU, precisão, save e resume, dataloader e export smoke passam, com driver e compute capability registrados | parar e corrigir a matriz |
| **G1** Mapeamento | massa de notas resolvida para papel específico publicada por coleção; nenhuma coleção acima de 10% em `other_percussion` entra no treino | remapear ou excluir a coleção |
| **G2** Dataset | duas builds independentes dão digests idênticos; round-trip exato em 100% dos exemplos; zero coincidência de hash exato, canônico ou rítmico entre blind test e train+validation; maior componente de cluster abaixo de 5% dos exemplos | não treinar |
| **G3** Representação | fração de notas não representável medida, publicada e menor ou igual ao orçamento declarado antes do build | revisar grade ou IR |
| **G4** Tiny | overfit deliberado abaixo do limiar declarado em 32–256 exemplos; 100% de saída estruturalmente válida; entropia entre seeds acima do piso declarado | corrigir pipeline ou modelo |
| **G5** Bake-off | challenger vence o melhor baseline em pelo menos três seeds na métrica primária declarada de validation, com margem maior que o desvio entre seeds do próprio baseline | não escalar |
| **G6** Full | blind test com ≥21/30 pareado; coincidência exata contra o train abaixo da coincidência interna do corpus; zero violação de lane bloqueada; resposta monotônica dos controles declarados | deterministic permanece |
| **G7** ONNX | suíte dourada dentro da tolerância por saída, incluindo a sequência completa de decoding; os sete limites da seção 19.4 respeitados em medição real | não integrar o modelo |
| **G8** Produto | os seis gates de runtime de `lab.py` passam contra os limiares de `gates.py`; o loop candidatos, locks, reference, falhas e readback passa no Live; tamanho da `.ablx` dentro do teto de O2 | não promover a `.ablx` |

`[decisão]` Cada gate produz `stop`, `repeat`, `go limited` ou `go`. Nenhum gate autoriza automaticamente o seguinte; o proprietário aprova a próxima despesa. Os limiares numéricos são congelados e versionados antes do run correspondente; alterar um limiar depois de ver o resultado invalida o gate e exige nova geração formal.

## 21. Planos de implementação

1. **Training workspace e environment probe** — projeto PyTorch isolado, locks, diagnósticos, smoke e checkpoint resume. Fecha E0/G0.
2. **Auditoria de corpus e mapa de articulações** — reproduz a seção 4.2 como código versionado; constrói o mapa de articulações por coleção e o mapa `collection → genre`; decompõe swing e jitter; mede clusters e duplicação cruzada no corpus inteiro. Não constrói dataset. Fecha D0/G1.
3. **Spike de orçamento CPU e ONNX** — exporta um modelo não treinado com a forma alvo (small, 32×18, decoding iterativo de N passos), mede contra os sete limites e devolve o número máximo de passos viável. Barato, e define a arquitetura antes de ela ser treinada. Fecha P0.
4. **Dataset foundation V3** — schema com `subhits`, canonical store, dedupe em camadas, cluster e split registry com guarda de componente gigante, shards e evidence packet. Fecha D1/G2/G3.
5. **Baselines e avaliação** — benchmark de retrieval e determinístico, GrooVAE, event AR, métricas e protocolo humano pré-registrado.
6. **Masked HVO Transformer** — tarefas, losses, decoding, tiny, 1% e 10%, bake-off. Fecha M0/M1/M2, G4 e G5.
7. **Full training e model card** — build 100%, run vencedor, blind test, anti-cópia e decisão registrada. Fecha M3/G6.
8. **ONNX provider** — export, equivalência, quantização, helper e orçamento, confirmando o spike do plano 3. Fecha R0/G7.
9. **Groove Brain product loop** — dashboard, prompt parser, candidatos, locks, reference, mapping e readback no Live. Fecha G8.

`[decisão]` A ordem tem duas inversões deliberadas em relação a um plano ingênuo. A auditoria de corpus vem antes da construção do dataset, porque o mapa de articulações muda a estrutura de lanes e refazer shards depois custa caro. E o orçamento de CPU vem antes do treino, porque descobrir depois que a arquitetura vencedora não cabe em `cpu_seconds <= 2,0` invalidaria dois planos inteiros.

Cada plano produz software testável e tem seu próprio stop condition. Nenhum plano de UI depende de modelo não promovido: o plano 9 usa baselines enquanto o treino evolui.

## 22. Riscos e respostas

1. **Mapeamento de articulações errado.** Maior severidade técnica. 24,3% da massa de notas cai em `other_percussion` e o chimbal está escondido lá. Resposta: mapa por coleção no plano 2, gate G1, e exclusão de coleção que não resolver.
3. **Grade densa perder rolls e flams por definição.** Medido em 3,51% / 1,38% / 0,92%. Resposta: canal `subhits` obrigatório e orçamento de perda declarado antes do build.
4. **Clustering colapsar em componente gigante.** Resposta: near-duplicate contínuo fora do fecho transitivo, distribuição publicada, teto de 5%.
5. **Vazamento por família baseada só em hierarquia.** Medido: `346` padrões e `1.030` esqueletos cruzam coleções. Resposta: teste de vazamento por conteúdo, independente do clustering.
6. **Corpus grande mas repetitivo.** 26,0% das janelas repetem padrão de onset exato. Resposta: contar famílias, não arquivos; curva de escala; originalidade medida contra a coincidência interna do corpus.
7. **Condições prometidas sem dados.** Gênero, subgênero e techno não existem na taxonomia. Resposta: só entram com mapa auditado e cobertura medida.
8. **Microtiming confundido com swing.** Resposta: decomposição viés/resíduo antes de promover `humanize`.
9. **Orçamento de CPU inviabilizar a arquitetura tarde demais.** `cpu_seconds <= 2,0` é teto de schema. Resposta: spike no plano 3.
10. **AR melhor em rolls mas lento.** Resposta: arquitetura híbrida ou AR restrito a pós-processamento, e só se o bake-off justificar.
11. **ONNX mudar o resultado.** Resposta: equivalência em logits, sequência de decoding, eventos e métricas antes de qualquer quantização.
12. **Memorização.** Resposta: split por família, canaries, nearest-neighbor e blind test fechado; anti-cópia como gate.
13. **Métrica boa e música ruim.** Resposta: escuta cega contra o melhor baseline é gate, não demonstração.
14. **Dependências de treino contaminarem o produto.** Resposta: projetos e locks separados; o usuário recebe só runtime nativo.
14. **`.ablx` crescer demais.** Resposta: CPU primeiro, modelo small, quantização depois da qualidade, teto de pacote antes da integração (O2).
15. **Protótipos sujos confundirem baseline.** Resposta: baseline é `HEAD` mais digests promovidos; o seed local de 500 e scripts com caminho fixo ficam fora.
16. **SDK e host em beta.** O produto depende de `@ableton-extensions/sdk` `1.0.0-beta.0` e de um build beta do Live; a API pode mudar e o Gate 0 só prova o host testado. Resposta: registrar build do Live e versão do host em cada evidência, e não escrever plano que assuma estabilidade de API.
17. **Pesquisa virar projeto infinito.** Resposta: cada degrau tem stop, e o produto determinístico continua útil se o neural falhar.

## 23. Decisões finais

- Groove Brain é bateria e ritmo, não Music Brain geral.
- Este é um experimento pessoal e local. Nada é vendido, publicado ou distribuído, e o programa não carrega gate de direitos. A proveniência é registrada porque dedupe, famílias e splits dependem dela.
- O mapa de articulações por coleção é pré-requisito do dataset. Sem ele, um quarto da massa de notas está na lane errada.
- O seed V2 de 1.685 itens é baseline de retrieval, não dataset de treino.
- O corpus completo precisa de remapeamento, near-dedupe, famílias e splits antes de qualquer treino sério.
- HVO com multiplicidade mais envelope lossless é a representação principal; event-based é challenger e proteção contra perda de rolls e flams.
- Masked Transformer é challenger recomendado, não vencedor pré-declarado.
- GrooVAE e event AR são baselines neurais obrigatórios.
- `humanize` tem base medida e só é promovido depois da decomposição swing/resíduo.
- PyTorch e CUDA são exclusivos do laboratório; o produto usa ONNX e runtime nativo local.
- CPU é o caminho universal; aceleração é opcional.
- O modelo precisa vencer retrieval e determinístico em avaliação cega e em anti-cópia.
- O diferencial da extensão é garantia, não tamanho de modelo: local, sem sobrescrita silenciosa, locks por construção, procedência em toda saída, e útil mesmo sem o neural.
- Nenhum treino full, integração neural, push, lançamento ou publicação é autorizado por esta especificação.

## 24. Fontes primárias

- [GrooVAE — Learning to Groove with Inverse Sequence Transformations](https://proceedings.mlr.press/v97/gillick19a.html)
- [Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove)
- [Magenta MusicVAE/GrooVAE — referência de arquitetura (repositório arquivado)](https://github.com/magenta/magenta/tree/main/magenta/models/music_vae)
- [GrooveTransformer — fonte e documentação de HVO](https://github.com/behzadhaki/GrooveTransformer)
- [Transformer Groove Infilling](https://transformergrooveinfilling.github.io/)
- [PocketVAE](https://arxiv.org/abs/2107.05009)
- [Conditional Drums Generation using Compound Word Representations](https://arxiv.org/abs/2202.04464)
- [PyTorch 2.12 — release e matriz CUDA/Blackwell](https://pytorch.org/blog/pytorch-2-12-release-blog/)
- [ONNX Runtime — execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [ONNX Runtime — model optimizations](https://onnxruntime.ai/docs/performance/model-optimizations/)
- [ONNX Runtime — quantização](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
- [microsoft/DirectML — aviso de manutenção](https://github.com/microsoft/DirectML)
- [DirectML — introdução, Microsoft Learn](https://learn.microsoft.com/en-us/windows/ai/directml/dml)

Verificações feitas em 2026-08-31: todos os links foram abertos; título e autoria de GrooVAE, PocketVAE e Conditional Drums Generation conferem; `magenta/magenta` está arquivado desde 2026-01-06; a afirmação sobre manutenção do DirectML e sobre Windows ML não está na página de execution providers do ONNX Runtime, e a fonte primária correta é o repositório `microsoft/DirectML`.

## 25. Critério de aprovação

Esta especificação vira planos executáveis quando o proprietário confirmar:

1. o escopo exclusivo de bateria e ritmo;
2. que o mapa de articulações por coleção é pré-requisito do dataset, e que exportar os mapas MIDI oficiais das bibliotecas instaladas é tarefa dele;
3. a comparação A/B/C em vez de treinar um modelo grande direto;
4. dataset, split e anti-cópia antes do full run;
5. promoção somente após avaliação cega;
6. a separação entre laboratório PyTorch e produto ONNX `.ablx`;
7. a decomposição em nove planos, com auditoria de corpus e spike de CPU antes do dataset e do treino.

**O1** e **O2** não impedem começar. O1 precisa estar respondida antes de coletar o teste cego (gate G5); O2, antes do plano 8.
