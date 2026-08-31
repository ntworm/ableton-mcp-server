# Groove Brain — design canônico de dataset e treinamento neural

- **Status:** revisada de forma adversarial em 2026-08-31 contra o commit-base `721e77b`. Bloqueada na pergunta O1 (seção 2.1). Planos 1, 2 e 3 da seção 18 podem ser escritos; do 4 em diante, não
- **Data:** 2026-08-31
- **Projeto:** `ableton-mcp-server`
- **Escopo:** bateria e ritmo MIDI; nenhum Composer Brain, lançamento ou publicação
- **Origem do corpus:** declarada pelo proprietário como material próprio e autorizado; a evidência medida na seção 2.1 não sustenta essa leitura, e a pergunta bloqueante O1 está aberta
- **Documento de produto relacionado:** [Groove Brain Extension](2026-08-30-groove-brain-extension-design.md)

## 1. Decisão em uma frase

Groove Brain será treinado como um sistema rítmico híbrido: o corpus privado passa por canonicalização lossless, deduplicação exata/canônica/próxima e splits por família; três modelos são comparados sob o mesmo orçamento; um Transformer HVO condicional e mascarado é o challenger principal, mas só avança se vencer retrieval, transformações determinísticas, GrooVAE e um decoder event-based em qualidade cega, originalidade e custo local; o vencedor é exportado para ONNX e executado offline por um helper isolado da Extension.

## 2. Correções e precedência

Este documento é a fonte de verdade para **dados e treinamento neural do Groove Brain**. Ele substitui, somente nesse domínio:

- as seções 13.4–13.6, 14, 16 e 17 de `2026-08-30-groove-brain-extension-design.md` quando houver conflito, isto é, pipeline de preparação, labels, split, representação musical, modelo neural e anti-memorização. A seção 13.3 (corpus bruto fora do Git) e a seção 15 (busca e referência) continuam valendo como estão;
- as decisões gerais de Music Brain sobre Composer Brain, REMI+ e composição multitrack.

### 2.1 Declaração de origem e evidência medida

O proprietário declarou que os padrões MIDI foram gerados/exportados por processo próprio, pertencem a ele e estão autorizados para este trabalho. Essa declaração fica registrada como evidência de origem do projeto e não constitui certificação jurídica independente.

A revisão de 2026-08-31 mediu o material real. O registro precisa conviver com estes fatos verificados:

- a raiz do corpus é `C:\Users\Usuario\Desktop\AUDIO_PRODUCTION\AUDIO\Superior Drummer 3\Toontrack\Midi` (`scripts/ingest_private_corpus.py:18`);
- as 280 `collection` do catálogo são nomes de produtos comerciais de terceiros. As maiores: `ezx_drumkit_from_hell` (19.756), `ezd_pop_rock` (8.550), `ezx_latin_percussion` (6.786), `real_blues` (4.657), `zildjian_artists` (4.270), `groove_monkee_progressive` (3.868), `ezdrummer_3` (2.879), `brooks_wackerman_grooves` (1.811) e `platinum_samples` (1.614);
- os `payloads` do seed publicado guardam bytes idênticos aos arquivos de origem. O artefato `ga1_ecdd85c8…` descomprime para os 242 bytes de `.../1921@EZX_DRUMS_OF_DESTRUCTION/100-S0299@FILLS/Variation_05.mid`, com SHA-256 igual ao registrado no catálogo;
- `license_id="user-owned"` e `redistribution="full"` não são derivados de evidência alguma: são constantes literais em `ableton_mcp_server/groove_intelligence/corpus.py:606-617`, aplicadas a 100% dos itens (facet `license=full` em 180.614 de 180.614).

"Exportado por processo próprio a partir de bibliotecas licenciadas" e "os arquivos são meus e podem ser redistribuídos" são afirmações diferentes. A evidência acima é compatível com a primeira e não sustenta a segunda: os bytes coincidem com o conteúdo distribuído pelos pacotes, na hierarquia e na convenção de nomes desses pacotes. O repositório é público e MIT, e `ableton_mcp_server/resources/groove_seed/index.sqlite`, versionado desde `aa680c7`, já distribui esses bytes.

**Pergunta bloqueante O1.** Antes de qualquer build de dataset, model card ou publicação, o proprietário precisa escolher uma posição:

- **(a)** o corpus é material de terceiros usado apenas localmente. `redistribution` passa a `derived_only` ou `blocked`, e o seed com payloads brutos sai do pacote público;
- **(b)** existe autorização de redistribuição documentável, que é anexada como evidência verificável por item e substitui a constante;
- **(c)** o treino segue apenas com o subconjunto de origem comprovadamente própria, medido e separado.

Enquanto O1 estiver aberta, o programa pode executar D0 (auditoria estatística sobre o catálogo existente) e E0 (probe de ambiente), e não pode executar D1 em diante.

Continuam válidas as decisões de produto:

- bateria/ritmo somente;
- operação local e offline;
- uma única instalação `.ablx` para o produto final;
- UI web servida localmente;
- Extension como única camada autorizada a tocar o Live;
- candidatos antes de escrita;
- aplicação explícita, revalidação e readback;
- modelo e inferência fora da thread/host do Ableton.

## 3. Estado real encontrado

### 3.1 Corpus medido

O inventário preservado em `%LOCALAPPDATA%\AbletonMCPServer\groove-build-v2\` (`ingestion-report.json` e `catalog_v2.sqlite`) registra:

- `183.429` arquivos descobertos e processados;
- `180.614` MIDIs válidos;
- `2.815` falhas de parser, todas com o mesmo reason code `groove_midi_error`;
- `11.296` repetições por digest bruto, restando `169.318` arquivos únicos por bytes;
- `99.933.371` bytes de MIDI bruto;
- predominância de loops curtos de bateria;
- rótulos úteis, porém fracos, na hierarquia de diretórios.

O seed de retrieval passou por duas gerações:

- V1: `2.048` representantes (`groove-build-v1/corpus-report.json`);
- V2 canônico no `HEAD`: `1.685` representantes em `groove.index.v2` após a mudança de representação/taxonomia.

Existe uma experiência local não commitada que substitui o seed por `500` itens (`manifest.json` da árvore de trabalho). Ela não é baseline, dataset de treino nem artefato promovido; o baseline é o `HEAD`.

### 3.1.1 Medições da auditoria D0 antecipada

Números apurados sobre o catálogo completo e sobre amostras aleatórias de arquivos únicos por bytes, com seed `20260831`. Eles substituem estimativas e devem ser reproduzidos e versionados pelo plano D0.

| Medida | Valor | Escopo |
|---|---|---|
| Compasso 4/4 | `155.844` (86,3%) | catálogo completo |
| Demais compassos | `24.770` (13,7%), sendo 6/8 `10.002`, 3/4 `5.995`, 7/8 `1.853`, 5/4 `1.646` | catálogo completo |
| Arquivos com menos de 2 barras | `56.842` de `169.318` (33,6%) | únicos por bytes |
| Janelas de 2 barras sem sobreposição | `354.749` | únicos por bytes |
| `offset_std` mediano | `9,76` ticks canônicos (PPQ 480), ≈10,2 ms a 120 BPM | catálogo completo |
| Arquivos com `offset_std` ≥ 10 ms a 120 BPM | 74,5% | catálogo completo |
| Arquivos perfeitamente quantizados (`offset_std = 0`) | 1,3% | catálogo completo |
| `velocity_std` mediano | `0,196` normalizado (≈25 unidades MIDI) | catálogo completo |
| Notas fundidas por célula em grade de 16 avos | 3,51% das notas; 36,6% dos arquivos afetados | amostra de 4.000 |
| Idem em grade de 32 avos | 1,38% das notas; 18,9% dos arquivos | amostra de 4.000 |
| Idem em grade de 64 avos | 0,92% das notas; 13,0% dos arquivos | amostra de 4.000 |
| Padrões de onset de 2 barras únicos | 82,4% (34.351 de 41.697 janelas) | amostra de 20.000 |
| Janelas em padrão de onset repetido | 26,0% | amostra de 20.000 |
| Padrões repetidos que cruzam `collection` | 9,9% (346 padrões); 1.030 esqueletos kick+snare | amostra de 20.000 |
| Arquivos com tempo meta no SMF | 97,8% | amostra de 1.000 |
| Cobertura de facet `style` | `103.265` (57,2%) | catálogo completo |
| Cobertura de facet `section` | `151.678` (84,0%) | catálogo completo |
| Facets `genre`, `subgenre` e `bpm` | não existem na taxonomia atual | catálogo completo |
| Coleções eletrônicas/techno/hip-hop somadas | `8.167` (4,5%); estritamente eletrônicas ≈`3.174` (1,8%) | catálogo completo |

Leitura direta desses números:

- o corpus tem microtiming e dinâmica reais, não é uma grade quantizada;
- o corpus é diverso, mas 26% das janelas repetem um padrão de onset exato mesmo depois da deduplicação por bytes, e 9,9% desses padrões repetidos aparecem em coleções diferentes;
- nenhuma grade densa de uma nota por célula representa o corpus sem perda;
- techno, dark techno e gênero/subgênero em geral não têm cobertura suficiente para virar condição do modelo hoje.

### 3.2 Fundação já implementada

O repositório já contém:

- parser e serializer SMF com limites;
- envelope MIDI lossless;
- ontologia de 18 papéis de bateria;
- projeções `groove.hvo.v2`, `groove.features.v2` e `groove.grammar.v2`;
- inventário reiniciável, hashes, proveniência, direitos e manifests;
- taxonomia de collection, genre, subgenre, style, section e source category;
- SQLite imutável para retrieval;
- busca, evidence, comparação e similaridade;
- geração determinística, transformações e recombinação multi-parent;
- mapping tardio e aplicação guardada no Live;
- protocolo de provider neural, subprocesso isolado, limites, fallback e gates;
- Gate 0 `.ablx` com helper local e write/readback observado no Ableton.

### 3.3 O que não existe

Não existe atualmente:

- dataset tensorial de treino;
- cluster de near-duplicates e registro de splits;
- loader de treino;
- arquitetura PyTorch do modelo;
- loss, optimizer, scheduler ou checkpoint;
- harness de experimento de **treino** e comparação entre arquiteturas;
- modelo treinado ou promovido;
- export ONNX validado;
- inferência neural dentro do helper `.ablx`;
- dashboard final do Groove Brain.

Existe, porém, um harness de gates de **runtime** já implementado, que esta especificação não pode ignorar nem duplicar: `groove_intelligence/gates.py` publica limiares (`quality_hvo_f1_min=0.90`, `p95_latency_seconds_max=5.0`, `peak_memory_mib_max=512`, `response_bytes_max=262144`, `candidate_events_max=2048`), `lab.py` executa os seis gates `contract`, `fallback`, `reproducibility`, `quality`, `privacy_license` e `cost_latency`, e `promotion.py` assina a decisão. Os gates G7 e G8 da seção 17 devem ser expressos nesse vocabulário existente, não em um vocabulário paralelo.

O `NeuralSubprocessProvider` atual é uma fronteira de segurança, não uma IA treinada. O código antigo de `music_brain` e o branch `wip/music-brain` são heurísticos e permanecem apenas como baselines ou material de descarte seletivo.

## 4. Objetivo mensurável da V1 neural

O primeiro modelo deve gerar e editar grooves curtos de bateria que:

1. respeitem as condições que passarem no gate de cobertura da seção 10.2. O conjunto mínimo hoje sustentado por dados é BPM, compasso, seção/função, densidade, energia, swing, complexidade e lanes bloqueadas. Estilo, gênero e subgênero só entram depois que a taxonomia passar a produzi-los com cobertura medida;
2. façam geração livre, variação, fill, infill temporal, infill de lanes e continuação curta;
3. preservem velocity e microtiming quando o corpus realmente contiver expressão útil;
4. usem um clipe do Ableton como referência com força controlável;
5. retornem vários candidatos reprodutíveis por seed;
6. não copiem silenciosamente um item ou uma família do treino;
7. executem localmente dentro do orçamento da `.ablx`;
8. superem o melhor baseline em avaliação cega.

### 4.1 Não objetivos

- melodia, baixo, harmonia ou arranjo;
- áudio generativo ou síntese de sons;
- canções completas;
- LLM de linguagem como gerador central;
- inferência online;
- treinamento no computador do usuário final;
- substituir o Ableton como editor;
- escalar parâmetros antes de provar dados, controles e avaliação;
- prometer humanização humana se o corpus não tiver performance humana suficiente.

## 5. Abordagens comparadas

### 5.1 A — Transformer HVO condicional e mascarado — recomendado como challenger

Entrada densa por tempo e papel de bateria; heads separados predizem hit, velocity e offset. Máscaras representam exatamente locks, lanes e regiões escolhidas. Decoding iterativo permite geração, infill e variação com o mesmo backbone.

**Vantagens:** controles diretos; paralelização; alinhamento natural com o HVO já implementado; preservação explícita de lanes; inferência curta; export relativamente simples.

**Riscos:** células densas escondem rolls/flams — medido em 3,51% das notas em 16 avos e 0,92% em 64 avos (seção 3.1.1), o que torna o canal `subhits` obrigatório em vez de opcional; geração totalmente mascarada exige decoding calibrado, e cada passo de decoding consome do teto de `cpu_seconds <= 2,0` da seção 16.4; probabilidades de hit podem colapsar para padrões médios.

### 5.2 B — decoder autoregressivo event-based — challenger obrigatório

Eventos carregam posição/delta, lane, velocity, offset e duração. O modelo prediz a sequência seguinte sob condições e grammar mask.

**Vantagens:** representa múltiplos hits, rolls e durações sem fundi-los; continuidade temporal é natural.

**Riscos:** inferência sequencial mais lenta; locks e infill exigem atenção/ordenação cuidadosas; sequências e invalidade estrutural podem crescer.

### 5.3 C — GrooVAE/HVO — baseline neural obrigatório

Baseline baseado na família GrooVAE, separando score de expressão e reconstruindo hit/velocity/microtiming através de espaço latente.

**Vantagens:** referência reproduzível; interpolação e humanização bem estudadas; custo pequeno.

**Riscos:** reconstrução e amostragem disputam o mesmo espaço; controle fino por região/lane é menos direto; stack Magenta histórico não deve virar runtime do produto.

### 5.4 Decisão

Não haverá votação por training loss. A mesma divisão de dados, tarefas, orçamento de passos, seeds e protocolo humano compara A, B e C. O Transformer HVO recebe prioridade de engenharia porque se encaixa melhor no produto, mas pode perder. Se nenhum neural vencer retrieval + transformações, o produto continua determinístico e o treino para.

Diffusion e modelo de texto não entram no primeiro bake-off: ampliam complexidade sem resolver uma deficiência demonstrada pelos três candidatos.

## 6. Arquitetura do programa

```text
corpus MIDI privado (read-only)
            |
            v
 inventário + rights/source manifest
            |
            v
 parser SMF -> IR lossless -> ontologia de lanes
            |
            +--> fingerprints + exact/canonical/near dedupe
            |                         |
            |                         v
            |                 clusters de família
            |                         |
            v                         v
 janelas + condições --------> train / validation / blind test
            |
            +--> HVO dense shards
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
                   export ONNX + equivalência
                              |
                              v
              provider local isolado -> candidates -> verifier
                              |
                        aprovação humana
                              |
                              v
                 Extension write + readback no Live
```

Treinamento e produto têm dependências separadas. PyTorch, CUDA, notebooks e ferramentas de análise nunca entram no runtime do usuário.

## 7. Contratos de dados

### 7.1 `SourceRecord`

Cada arquivo recebe um registro imutável com:

- `source_id` estável e não baseado em caminho público;
- hash bruto e tamanho;
- caminho relativo somente no catálogo privado;
- `source_kind` e `license_id` derivados da resposta a O1 (seção 2.1), **por item e a partir de evidência**, nunca de constante literal como hoje;
- `redistribution` derivado da mesma resposta;
- evidência da declaração de origem/autorização, com digest e data;
- parser/normalizer/taxonomy versions;
- status e reason code;
- lineage disponível do gerador anterior;
- família de origem inferida e confiança.

Nomes de marcas podem ser usados localmente para interpretar mapping/hierarquia, mas não aparecem em pesos, cards públicos ou nomes de produto quando forem desnecessários.

### 7.2 `CanonicalGroove`

O objeto canônico liga:

- envelope MIDI lossless;
- tempo, compasso, PPQ e comprimento musical;
- eventos normalizados e papéis de bateria;
- projeção HVO;
- sequência event-based;
- features e taxonomy labels com confiança;
- hashes bruto, canônico, rítmico e de expressão;
- `family_cluster_id`;
- `split_id`;
- flags de qualidade, colisão, truncamento e expressão.

Modelo nunca abre `.mid` diretamente. Ele consome uma projeção versionada do `CanonicalGroove`.

### 7.3 `DatasetManifest`

O manifest de uma build registra:

- seleção exata de fontes e digests;
- versões de parser, normalizer, ontology, fingerprint e tokenizer;
- regras de janela, grid e subeventos;
- algoritmo e thresholds de clustering;
- seed e algoritmo do split;
- contagens por split, gênero, seção, compasso, BPM, lane e família;
- descarte por reason code;
- digests dos shards;
- matriz de direitos;
- data, ambiente e comando reproduzível.

Dataset, shards e envelopes ficam fora do Git. O repositório recebe somente schemas, código, fixtures sintéticas e relatórios sanitizados.

A árvore atual não cumpre essa regra e o conflito precisa ficar registrado, não implícito: `ableton_mcp_server/resources/groove_seed/index.sqlite` é versionado desde `aa680c7` e sua tabela `payloads` guarda MIDI bruto comprimido, byte a byte igual aos arquivos de origem. O mesmo vale para a seção 13.3 do documento de produto, que afirma que MIDIs brutos permanecem fora do repositório. Resolver isso depende da resposta a O1 e é pré-requisito do plano 2, não trabalho posterior.

## 8. Canonicalização musical

### 8.1 Ontologia

A V1 mantém os 18 papéis existentes: kick, snare, rim, clap, closed/open/pedal hat, low/mid/high tom, crash, splash, china, ride, ride bell, tambourine, cowbell e other percussion.

Pitch de origem é preservado no envelope. Modelo aprende papel canônico; mapping para Drum Rack/SD3 acontece depois da geração.

### 8.2 Grade e microtiming

O pipeline mede antes de escolher:

- colisões por lane/célula em grid de 16 avos;
- cobertura adicional com 32 avos;
- distribuição de offsets;
- quantidade de rolls/flams e múltiplos eventos;
- comprimento e compassos reais.

Essas medidas já foram tomadas na auditoria antecipada (seção 3.1.1) e o resultado é decisivo: **nenhuma grade densa de uma nota por célula representa o corpus sem perda**. Fundindo por `(papel, barra, passo)`, perdem-se 3,51% das notas em 16 avos (36,6% dos arquivos afetados), 1,38% em 32 avos e 0,92% em 64 avos. Aumentar a grade reduz o problema e não o elimina, porque flams e rolls ficam sistematicamente abaixo de qualquer célula praticável.

Consequências obrigatórias:

- a projeção atual `groove.hvo.v2` **funde silenciosamente**: `derive_hvo` agrupa por `(papel, barra, passo)` e grava `hit=1` com média de velocity e de offset (`groove_intelligence/projections.py:85-108`). Ela serve retrieval e não serve como alvo de treino;
- o tensor HVO de treino precisa de um canal explícito de multiplicidade — no mínimo `subhits` inteiro por célula e um `collision_flag` — mais a referência ao envelope, de modo que o round-trip do alvo de treino seja exato e a perda seja atribuída à política, nunca ao silêncio;
- a política de versão do dataset declara, por escrito e por número, quanto da massa de notas cada representação descarta, e o `DatasetManifest` publica esse número.

Baseline inicial: duas barras em 4/4, 32 passos de semicolcheia, offset contínuo, com canal de multiplicidade. Challenger de 64 passos entra se reduzir perda relevante — a medição já indica queda de 3,51% para 1,38% da massa de notas. Subeventos continuam no envelope e alimentam o decoder event-based.

Outros compassos são preservados no IR e avaliados separadamente. Eles só entram no modelo V1 se houver cobertura mínima por split; caso contrário permanecem no retrieval e são explicitamente fora de distribuição para geração neural. Hoje 4/4 cobre 86,3% do corpus e 6/8 é o segundo maior grupo, com `10.002` arquivos: é o único candidato realista a um segundo compasso na V1.

### 8.3 Tensores

Os shards HVO armazenam separadamente:

- `hit`: booleano/uint8 `[example, time, lane]`;
- `subhits`: uint8 `[example, time, lane]` com a contagem real de eventos na célula, e `collision_flag` derivado, para que a fusão deixe de ser silenciosa;
- `velocity`: float normalizado, com loss mask por hit;
- `offset`: deslocamento normalizado pela célula, com loss mask por hit;
- `observed_mask`: posições fornecidas ao modelo;
- `target_mask`: posições cobradas pela tarefa;
- condições categóricas e contínuas;
- IDs opacos de exemplo, família e origem.

Ordem de grandeza do formato denso, para dimensionar disco antes de construir: 32 passos × 18 lanes = 576 células por exemplo; em float32 para velocity/offset e uint8 para o resto são ≈6,2 KiB por exemplo. Com `354.749` janelas sem sobreposição isso dá ≈2,2 GB, e ≈4,4 GB com hop de uma barra. O dataset denso completo fica na casa das unidades de GB, não das centenas.

Shards event-based armazenam tokens/atributos equivalentes e apontam para o mesmo exemplo canônico. O formato físico é sharded e content-addressed, com arrays NumPy mmap-friendly e índice JSONL canônico; nenhum pickle é aceito.

### 8.4 Janela

Unidade primária: duas barras. Arquivos maiores geram janelas com sobreposição somente depois de o split por família ser definido. Janelas do mesmo arquivo ou família nunca atravessam splits. Fills podem usar uma barra de contexto + região-alvo final; continuação curta usa contexto anterior explícito.

`33,6%` dos arquivos únicos têm menos de duas barras, o que a versão anterior deste documento não tratava. A política é explícita: um arquivo de uma barra vira uma janela de duas barras por repetição da barra, marcada com `looped=true`, ou é mantido como janela de uma barra com o resto em `observed_mask=0` e `target_mask=0`. A escolha entre as duas é uma ablação de D1, e o `DatasetManifest` registra qual foi usada e quantos exemplos ela produziu. Repetir a barra sem marcar a flag é proibido: cria periodicidade artificial de duas barras que o modelo aprenderia como estrutura.

## 9. Dedupe, famílias e splits

### 9.1 Camadas de deduplicação

1. bytes idênticos;
2. eventos equivalentes após remover metadados irrelevantes;
3. equivalência rítmica por lanes, ignorando mapping de pitch;
4. near-duplicate por distância HVO/grammar/features;
5. família por hierarquia, lineage do gerador anterior e assinaturas de geração.

Thresholds de near-duplicate são calibrados com pares exatos, variações conhecidas e pares musicais diferentes. Eles são congelados antes de abrir o blind test.

O `family_cluster_id` é o fecho transitivo sobre a união das arestas das camadas 1, 2, 3 e 5. A camada 4 (near-duplicate contínuo) **não** cria aresta de cluster por padrão, porque single-linkage sobre distância contínua colapsa em um componente gigante e torna o split 80/10/10 impossível. Ela entra como filtro de amostragem e como métrica publicada. Se o plano D1 quiser promovê-la a aresta, precisa antes publicar a distribuição de tamanho de componente e provar que o maior componente fica abaixo de 5% dos exemplos; acima disso, o clustering é rejeitado e o threshold é reduzido.

A camada 5 (família por hierarquia) é insuficiente sozinha e não pode ser a única chave de agrupamento. Na amostra de 20.000 arquivos únicos por bytes, `346` padrões de onset de 2 barras repetidos (9,9% dos padrões repetidos) e `1.030` esqueletos de kick+snare aparecem em `collection` diferentes. Agrupar só por diretório deixaria essas cópias em lados opostos do split e o gate G2 passaria mesmo assim.

### 9.2 Falta de lineage

Se prompt/template/batch/seed do gerador original existirem, são usados apenas no catálogo privado. Se não existirem, o sistema combina:

- origem/hierarquia;
- canonical hash;
- fingerprint de hits por lane;
- assinatura de velocity/offset;
- comprimento, BPM, seção e taxonomia;
- clustering conservador por similaridade.

A ausência de lineage não bloqueia experimento, mas reduz a força da alegação de generalização e aparece no model card.

### 9.3 Split

Ordem obrigatória:

1. construir clusters sem olhar métricas do modelo;
2. reservar blind test por cluster/família;
3. dividir o restante em train e validation;
4. estratificar aproximadamente por estilo, seção, BPM, compasso e cobertura de lanes sem quebrar clusters;
5. congelar IDs e digests;
6. treinar normalizadores, embeddings e qualquer vocabulário somente no train;
7. impedir retrieval de consultar validation/test durante avaliação neural.

Alvo inicial: aproximadamente 80/10/10 por exemplos, subordinado a clusters inteiros. O relatório publica o desvio real e falha se qualquer hash exato, canônico ou cluster conhecido atravessar a fronteira.

Duas verificações são obrigatórias e não opcionais, porque a auditoria mostrou que a hierarquia sozinha vaza:

1. o relatório publica a distribuição de tamanho dos clusters, o maior componente em percentual de exemplos e o desvio real do 80/10/10 alcançável sob a restrição de clusters inteiros. Se o maior componente impedir o alvo, a resposta é reduzir threshold e reagrupar, nunca quebrar um cluster;
2. um teste de vazamento por conteúdo, independente do clustering, compara os hashes exato, canônico e rítmico de todo o blind test contra todo o train e o validation. Qualquer coincidência é falha de build, não observação.

## 10. Labels e condições

### 10.1 Weak labels

Nomes de diretório fornecem sinais de style, section e feel, mas não verdade absoluta. Cada label carrega origem e confiança. Aliases passam pela taxonomia V2; categorias raras ou ambíguas viram `unknown`/hierarquia genérica em vez de rótulo inventado.

Cobertura real medida na taxonomia atual, que corrige o que a versão anterior deste documento supunha:

- `section`: `151.678` de `180.614` (84,0%), dominada por `variation` (101.372), `groove` (45.146) e `fill` (39.956);
- `style`: `103.265` (57,2%), dominada por `straight` (66.907) e `swing` (26.269);
- `feel`, `density`, `microtiming`, `kit` e `collection`: 100%;
- `genre` e `subgenre`: **não existem** como eixo da taxonomia;
- `bpm`: **não existe** como eixo da taxonomia.

BPM não vem do nome do diretório. `97,8%` dos arquivos carregam evento meta de tempo no próprio SMF, que é a fonte exata e deve ser a usada. Extrair BPM do caminho é pior e é contaminado: o prefixo numérico de coleção (`210@GROOVE_MONKEE_*`, `200241@REAL_BLUES`) é indistinguível de um token de andamento e produz `210` como valor mais frequente.

Gênero e subgênero, se forem necessários, precisam de um mapa explícito `collection → genre` construído e auditado à mão sobre as 280 coleções. Enquanto esse mapa não existir e não for medido, gênero e subgênero não são condição do modelo.

Um conjunto auditado manualmente mede precisão dos labels mais importantes: `fill` contra `groove`/`variation`, as seções nomeadas e o `style`. Techno e dark techno **saem** dessa lista de prioridade: as coleções eletrônicas somam `8.167` arquivos (4,5%), as estritamente eletrônicas ≈`3.174` (1,8%), e a interseção literal de techno com dark é da ordem de uma centena de arquivos. O corpus é de bateria acústica de rock, metal, blues, jazz, latin e pop. O dashboard só oferece condição cujo train split possui cobertura e qualidade mínimas, e techno não tem.

### 10.2 Condições do modelo

- estilo; gênero/subgênero somente depois do mapa auditado da seção 10.1;
- BPM normalizado, lido do evento meta de tempo do SMF;
- compasso;
- beat, fill e seção;
- densidade global e por lane;
- energia;
- complexidade;
- swing/feel;
- comprimento;
- lanes/regiões bloqueadas;
- força de mutação;
- embedding opcional de referência.

Condition dropout ensina modo parcialmente ou totalmente não condicionado. Controles contínuos são avaliados por resposta monotônica, não apenas classificação.

### 10.3 Texto livre

“Rock pesado 140 BPM com fill no fim” passa primeiro por parser local determinístico e produz uma `GrooveSpec` visível. Sinônimos multilíngues mapeiam para taxonomia e controles. Nenhum LLM é necessário. Modelo de linguagem local pequeno só poderá competir futuramente pela tradução de texto; nunca produz notas nem escreve no Live.

O exemplo mudou de propósito. Um pedido como “techno sombrio 128 BPM” precisa falhar de forma visível e honesta — a `GrooveSpec` mostra o termo como não coberto e o sistema oferece o mais próximo com aviso — em vez de devolver silenciosamente um groove de rock rotulado como techno. Termo sem cobertura no train split é erro de cobertura, não pedido inválido.

## 11. Tarefas de treinamento

Uma task sampler versionada cria exemplos sem mudar o split:

1. **free generation:** todas as células-alvo mascaradas;
2. **variation:** parte do groove observada e parte corrompida/mascarada;
3. **temporal infill:** região temporal contínua removida;
4. **lane infill:** uma ou mais lanes removidas;
5. **fill:** região final condicionada por seção/função;
6. **continuation:** bloco seguinte condicionado pelo anterior;
7. **humanize:** hits quantizados/velocity simplificada para expressão original;
8. **reference:** padrão-alvo condicionado por embedding do clipe de referência e força de similaridade.

`reference` só usa pares sustentados por família/style ou corrupção controlada; não cria pares aleatórios e chama isso de aprendizagem.

`humanize` deixa de ser hipótese aberta: a medição da seção 3.1.1 mostra `offset_std` mediano de 9,76 ticks canônicos (≈10,2 ms a 120 BPM), 74,5% dos arquivos acima de 10 ms, apenas 1,3% perfeitamente quantizados e `velocity_std` mediano de 0,196 normalizado. Há expressão suficiente para a tarefa existir. Resta uma condição, e ela é obrigatória antes de promover a tarefa: `offset_std` agregado **confunde swing e feel sistemáticos com jitter de performance**. D0 precisa decompor o offset em viés médio por `(papel, posição na grade)` e resíduo, e `humanize` só é promovido se o resíduo — não o viés — tiver variedade útil. Sem essa decomposição, um corpus perfeitamente swingado e perfeitamente rígido passaria no teste.

O Groove MIDI Dataset (1.150 arquivos, 13,6 h, performance humana capturada, CC BY 4.0) serve como benchmark/auxiliar separado para calibrar essa decomposição; ele não é misturado silenciosamente ao corpus principal.

Distribuição inicial de tarefas é hipótese registrada em config, nunca constante escondida. Ablations comparam task mix e removem tarefas que degradarem o núcleo.

## 12. Modelos e orçamento

### 12.1 Masked HVO

Arquitetura inicial:

- embeddings de lane, posição, tarefa e condições;
- Transformer encoder bidirecional;
- heads de hit, velocity e offset;
- BCE ou focal loss para hit conforme desbalanceamento;
- Smooth L1 para velocity/offset somente onde há hit;
- regularização de densidade/controle somente se ablation provar benefício;
- decoding iterativo de confiança com temperatura/threshold por lane.

Escala:

| Nível | Configuração indicativa | Função |
|---|---|---|
| smoke | 2 camadas, `d_model=128`, 4 heads | provar pipeline/overfit |
| small | 6 camadas, `d_model=256`, 8 heads, FFN 1024 | challenger principal inicial |
| medium | 8–10 camadas, `d_model=512`, FFN 2048 | somente se curva de escala justificar |

Ordem de grandeza dos blocos do encoder, sem embeddings: small ≈`4,7M` parâmetros (6 × (4·256² + 2·256·1024)); medium ≈`25M` a `31M` (8 a 10 × (4·512² + 2·512·2048)). O alvo antigo de 20–50M portanto descreve a faixa medium e nem chega ao topo dela. Contagem real é calculada e registrada. Modelo maior não avança se small já saturar dados ou qualidade.

Escala versus dados: `354.749` janelas × 576 células são ≈2,0·10⁸ células por época, das quais a fração realmente ocupada é pequena — a mediana é de 16 hits por barra, ou seja, ≈6% das células. O sinal efetivo por época é da ordem de 1,1·10⁷ hits. Um modelo de 25M parâmetros sobre esse volume é candidato natural a memorizar, o que reforça a seção 15.4 como gate e não como relatório.

### 12.2 Event-based AR

Decoder-only pequeno com embeddings fatorados de tempo, lane, velocity e offset; causal mask e grammar mask. Usa orçamento de parâmetros e passos comparável ao masked small. Avalia especialmente rolls, flams, continuidade e validade.

### 12.3 GrooVAE

Implementação reproduzível e moderna da tarefa de duas barras, sem copiar o stack legado para runtime. Config, conversão e métricas seguem a publicação original onde aplicável. Pesos publicados servem somente como referência; o comparativo principal treina no mesmo split permitido.

O repositório `magenta/magenta` foi arquivado pelo dono em 2026-01-06 e é somente leitura. Ele serve como referência de arquitetura e de configuração, não como dependência instalável nem como stack de execução. Reimplementar em PyTorch é a única rota compatível com a seção 13.1.

## 13. Ambiente e reprodutibilidade

### 13.1 Separação

- preparação/inventário: Windows ou Linux, usando contratos existentes;
- treinamento: ambiente Linux reproduzível;
- produto: Windows x64, helper nativo e ONNX Runtime sem Python;
- dados/checkpoints: workspace externo ao Git;
- manifests/fixtures/relatórios sanitizados: repositório.

### 13.2 GPU local

Ambiente verificado em 2026-08-31 nesta máquina: `NVIDIA GeForce RTX 5070`, `12227 MiB` de VRAM, driver `610.74`, compute capability `12.0` (Blackwell), CUDA UMD `13.3`, com 64 GB de RAM e i9-12900KS. É suficiente para smoke, small, ablations e, para o porte de modelo desta especificação, para o treino completo com mixed precision, gradient accumulation e activation checkpointing. A restrição real não é VRAM: um modelo small de ≈4,7M parâmetros cabe com folga, e a faixa medium de ≈25M também.

O documento anterior fixava PyTorch 2.7/CUDA 12.8. A linha oficial mudou: a partir do PyTorch 2.12 a wheel CUDA 12.8 está descontinuada, a wheel padrão é CUDA 13.0, CUDA 13.2 é experimental, e a orientação para GPUs Blackwell é usar wheels CUDA 13.0+, com driver mínimo `580.65.06` no Linux e `580.88` no Windows. O driver instalado (`610.74`) satisfaz o piso. A implementação não copia números deste texto cegamente; executa um environment probe, registra driver/GPU/compute capability, instala versões pinadas em lock e congela a matriz que passar smoke + checkpoint resume + determinismo declarado.

### 13.3 Determinismo

Cada run registra:

- commit e dirty-state digest;
- dataset/split/config digests;
- versões de Python, PyTorch, CUDA, cuDNN e drivers;
- GPU, precision e kernels;
- seed de Python/NumPy/PyTorch/data workers;
- sampler state, optimizer e scheduler;
- checkpoints e métricas.

Determinismo bit-a-bit entre GPUs não é prometido. Reprodutibilidade significa configuração e lineage completos, curvas compatíveis e output exato somente dentro da matriz declarada.

### 13.4 Disco e retenção

Antes do corpus completo, o pipeline mede o tamanho de 1% e projeta 10%/100%. Nenhum full build começa se dataset, caches, três runs e margem de rollback não couberem.

Estado de disco verificado em 2026-08-31: `C:` com `193 GB` livres de 1,9 TB (90% em uso), `D:` com `386 GB` livres de 5,5 TB, `F:` com `458 GB` livres de 1,9 TB. O corpus bruto ocupa `99.933.371` bytes de conteúdo. Pela estimativa da seção 8.3, o dataset denso completo fica na casa de 2 a 5 GB, e checkpoints de um modelo small ou medium com estados de optimizer ficam abaixo de 1 GB por checkpoint. **Disco não é o gargalo deste programa**; a projeção 1%/10%/100% continua obrigatória como prova de que o pipeline mede antes de escrever, não porque haja risco de estouro. O workspace de treino fica em `D:` ou `F:`, nunca em `C:`, que já está a 90%.

Política inicial:

- manter raw read-only;
- manter uma build de dataset promovida e uma candidata;
- por run, manter `best`, `last` e checkpoints de marco;
- apagar cache regenerável somente por comando explícito e path verificado;
- nunca usar o repositório, home ou raiz como alvo de limpeza.

## 14. Escada de treinamento

### 14.1 E0 — environment probe

Provar GPU, mixed precision, forward/backward, save/resume, DataLoader multiprocess e export de um grafo mínimo. Falha bloqueia qualquer run longo.

### 14.2 D0 — auditoria de dados

Executar estatísticas sobre 100% do catálogo já inventariado sem criar ainda o dataset final: expressão, colisões, lanes, barras, compassos, labels, famílias e duplicação próxima. Congelar políticas de inclusão.

A seção 3.1.1 já traz a primeira passada dessas medições, feita na revisão. D0 as reproduz como código versionado e acrescenta o que a revisão não fez: decomposição de offset em viés sistemático por `(papel, posição)` e resíduo, mapa auditado `collection → genre`, distribuição de tamanho de cluster e taxa de duplicação cruzando `collection` sobre o corpus inteiro em vez de amostra. D0 é executável mesmo com O1 aberta.

### 14.3 D1 — build de 1%

Criar duas builds idênticas, provar digests, splits e round-trip; verificar ausência de vazamento e estimar disco/throughput.

### 14.4 M0 — overfit controlado

Treinar smoke em 32–256 exemplos até memorizar deliberadamente. Prova loss masks, task sampler, checkpoint e decoding. Incapacidade de overfit é bug, não falta de escala.

### 14.5 M1 — tiny 1%

Rodar deterministic/retrieval, GrooVAE, event AR e masked HVO sob orçamento curto. Verificar geração válida, controle e ausência de colapso.

### 14.6 D2/M2 — dataset 10% e bake-off

Congelar representação, grids, thresholds e protocolo. Executar pelo menos três seeds por candidato. Selecionar arquitetura por validation + avaliação humana sem tocar blind test.

### 14.7 D3/M3 — full run

Construir dataset 100% somente depois dos gates anteriores. Treinar a configuração vencedora e uma baseline forte. Blind test abre uma vez para a decisão registrada.

### 14.8 M4 — controle e hard examples

Se o modelo full vencer, ajustar task mix/controles usando train+validation; rodar novo blind test versionado apenas se houver uma nova geração formal de dataset/modelo.

### 14.9 R0 — runtime optimization

Exportar FP32/FP16 quando aplicável e INT8 dinâmico para CPU. Quantização só é aceita se equivalência musical e qualidade passarem. Medir CPU antes de adicionar aceleração GPU.

R0 confirma, não descobre. O número que decide a arquitetura — quantos passos de decoding cabem em `cpu_seconds <= 2,0` — sai do spike do plano 3, com modelo não treinado, antes de M1. Se R0 contradisser o spike, o erro está no spike e a arquitetura é revista, não o limite.

## 15. Avaliação

### 15.1 Integridade

- parse e serialize válidos;
- 100% das saídas aceitas dentro de pitch/lane/time/length limits;
- zero violação de lanes/regiões bloqueadas;
- zero família/near-duplicate conhecida cruzando splits;
- nenhuma consulta do retriever ao blind test;
- zero evento perdido **sem registro**. A formulação anterior, “zero evento silenciosamente perdido”, era inatingível para qualquer grade densa: a medição mostra 3,51% das notas fundidas em 16 avos e ainda 0,92% em 64 avos. O critério verificável é duplo: (i) o round-trip `CanonicalGroove → tensor de treino → CanonicalGroove` é exato para 100% dos exemplos, com `subhits` e envelope, e (ii) a fração de notas não representável pela grade escolhida é medida, publicada no `DatasetManifest` e comparada com o orçamento declarado da versão. Perda acima do orçamento é falha de G3.

### 15.2 Predição

- precision/recall/F1 de hit por lane;
- velocity MAE/Smooth L1 condicionado a hit;
- offset MAE condicionado a hit;
- fill/infill por região e lane;
- calibração de probabilidade de hit;
- reconstruction e sampling medidos separadamente para VAE.

### 15.3 Musicalidade e controle

- aderência a densidade, energia, swing, complexidade e referência;
- resposta monotônica de controles contínuos;
- distribuição por lane e posição;
- diversidade intra-lote e entre seeds;
- silêncio, repetição e colapso;
- validade de rolls/flams;
- distância e cobertura em relação ao corpus.

### 15.4 Originalidade

Cada candidato é comparado ao train por:

- hash canônico;
- fingerprint HVO com invariâncias declaradas;
- grammar/features;
- sequência event-based;
- família e origem;
- cópia de trechos contíguos.

Limiar varia por tarefa: uma variação pode ser próxima da referência; free generation não pode reproduzir uma família inteira. Resultado acima do limiar é rejeitado/regenerado e contabilizado.

Os limiares são congelados antes do primeiro run de bake-off e registrados com digest, junto com uma referência que impede leitura complacente: no próprio corpus, 26,0% das janelas de 2 barras repetem exatamente o padrão de onset de outra janela. Um gerador que produzisse cópias exatas nessa mesma taxa seria indistinguível do corpus por essa métrica. Portanto o gate de originalidade mede a taxa de coincidência exata **contra o train** e exige que ela fique abaixo da taxa de coincidência interna do próprio corpus, não apenas “baixa”.

### 15.5 Teste humano

Protocolo pré-registrado:

- pelo menos 30 tarefas representativas;
- prompts/controles congelados;
- candidatos anonimizados e volume/kit normalizados;
- comparação neural contra melhor retrieval/transform determinístico;
- avaliação de groove, utilidade, controle, novidade e vontade de usar;
- ordem aleatória e identidade do sistema oculta;
- número de avaliadores, unidade de análise e tratamento de empates declarados **antes** de coletar;
- intervalo de confiança publicado.

Promoção exige que o limite inferior do intervalo para preferência pelo challenger seja maior que 50%, além dos gates automáticos. Com 30 comparações pareadas e empates excluídos do denominador, isso significa concretamente **≥21 de 30** vitórias (limite inferior de Wilson a 95% ≈ 0,521; 20 de 30 dá ≈ 0,488 e falha). Esse número é registrado antes da coleta e não é renegociado depois.

Limitação declarada: se o avaliador for uma pessoa só, o intervalo é sobre tarefas, não sobre pessoas, e o resultado não generaliza para outros músicos. Isso é aceitável como gate de decisão do proprietário e precisa aparecer no model card com essas palavras. Se não ocorrer preferência, deterministic/retrieval permanece produto principal.

## 16. Runtime e `.ablx`

### 16.1 Export

PyTorch exporta um grafo ONNX com inputs/outputs e dynamic axes mínimos, pela rota `torch.export`/exportador baseado em Dynamo. TorchScript está descontinuado desde o PyTorch 2.10, então o exportador legado baseado em trace não é rota suportada e não deve ser assumido. Uma suíte dourada compara logits, decoding e groove canônico entre PyTorch e ONNX, com tolerância numérica declarada por saída. Diferença além da tolerância bloqueia o artefato.

O decoding iterativo é parte do contrato de equivalência, não um detalhe do runtime: se o laço de decoding viver fora do grafo, a suíte dourada precisa comparar a sequência completa de passos, não só os logits do primeiro passo.

### 16.2 Provider

O helper recebe somente `ConditionCard`, referência canônica limitada, seed e limites. Ele não recebe caminho de corpus, comando, shell, token externo ou objeto do Live. Saída passa pelo parser, verifier, anti-copy e mapping antes de aparecer como candidato.

### 16.3 Execution providers

CPU é baseline universal. ONNX Runtime permite providers ordenados com fallback; aceleração GPU é opcional e só entra se estiver empacotada/compatível com single-install. CUDA no computador de desenvolvimento não vira requisito do usuário.

O repositório `microsoft/DirectML` declara explicitamente estado de manutenção, e a Microsoft direciona o desenvolvimento novo para Windows ML, que expõe as mesmas APIs do ONNX Runtime e seleciona o execution provider conforme o hardware. A página de execution providers do ONNX Runtime lista DirectML como provider de produção sem marca de depreciação e não menciona Windows ML, então as duas fontes precisam ser lidas juntas. Nenhuma das duas é selecionada sem spike de embalagem e equivalência.

Risco específico de Windows ML para este produto: ele resolve e provisiona execution providers pelo sistema operacional, o que conflita com as decisões de operação offline e instalação única em um `.ablx`. Se o spike mostrar que o provider precisa ser baixado sob demanda, Windows ML sai do caminho da V1 e o produto fica em CPU pura.

### 16.4 Orçamento preliminar

Os limites atuais não são metas de P95: são tetos rígidos por chamada, declarados em `ProviderLimitsV1` (`groove_intelligence/provider.py:49-59`) com `le=` no schema, ou seja, não podem sequer ser elevados por configuração. A versão anterior desta seção listava três deles e omitia os que mais apertam o decoding iterativo:

| Limite | Valor | Efeito no modelo |
|---|---|---|
| `generation_seconds` | `<=5,0` | teto de parede por chamada, não P95 |
| `cpu_seconds` | `<=2,0` | **teto de tempo de CPU somado entre threads**; com 8 threads são 0,25 s de parede |
| `startup_seconds` | `<=2,0` | carga de sessão ONNX e pesos precisa caber aqui |
| `shutdown_seconds` | `<=1,0` | encerramento limpo do helper |
| `memory_mib` | `<=512` | modelo, runtime e arena de execução |
| `max_response_bytes` | `<=262.144` | candidato serializado em JSON |
| `max_events` | `<=2.048` | eventos por candidato |

`cpu_seconds <= 2,0` é o limite que decide a viabilidade, e não aparecia no documento. Um decoding iterativo de N passos multiplica o custo por N; o plano do provider ONNX precisa orçar passos × threads dentro de 2 s de CPU, ou negociar formalmente uma alteração do contrato antes de projetar o decoding.

Demais itens do orçamento:

- alvo de produto: candidato warm aproximadamente `<=1 s` no hardware do autor;
- baseline medido de pacote: o `.ablx` do Gate 0 tem `154.852` bytes, com helper Rust de `258.048` bytes descomprimido. Qualquer runtime ONNX e pesos entram **acima** desse piso, e o documento de produto já fixa preferência por pacote core abaixo de 500 MiB;
- o plano do provider ONNX declara um teto numérico de tamanho da `.ablx` **antes** de escolher runtime e quantização, e não depois;
- cold start, tamanho do modelo e tamanho total da `.ablx` são medidos antes da promoção;
- nenhuma meta é relaxada depois de ver o blind test.

## 17. Gates binários

Um gate só é binário se o critério puder ser avaliado por outra pessoa sem consultar a intenção do autor. Os critérios abaixo substituem as formulações subjetivas da primeira versão (“publicada e aceita”, “humano preliminar”, “passam”).

| Gate | Passa quando | Falha significa |
|---|---|---|
| G0 Ambiente | GPU/precision/save-resume/dataloader/export smoke passam, com driver e compute capability registrados | parar e corrigir matriz |
| G1 Direitos/origem | a pergunta bloqueante O1 da seção 2.1 está respondida por escrito; `license_id` e `redistribution` de cada item derivam dessa resposta e de evidência verificável, **não** de constante de código; e o build falha se algum item ficar sem essa derivação | item fica fora; se O1 não estiver respondida, o programa para em D0 |
| G2 Dataset | duas builds independentes produzem digests idênticos; round-trip exato em 100% dos exemplos; zero coincidência de hash exato, canônico ou rítmico entre blind test e train+validation; maior componente de cluster abaixo de 5% dos exemplos | não treinar |
| G3 Representação | fração de notas não representável pela grade escolhida é medida, publicada no `DatasetManifest` e menor ou igual ao orçamento declarado antes do build; round-trip do alvo de treino exato | revisar grid/IR |
| G4 Tiny | overfit deliberado atinge perda de treino abaixo do limiar declarado em 32–256 exemplos; tiny runs geram saída estruturalmente válida em 100% dos casos; entropia de saída entre seeds acima do piso declarado | corrigir pipeline/modelo |
| G5 Bake-off | challenger vence o melhor baseline em pelo menos três seeds na métrica primária declarada de validation, com margem maior que o desvio entre seeds do próprio baseline | não escalar |
| G6 Full | blind test com ≥21/30 pareado (seção 15.5); taxa de coincidência exata contra train abaixo da coincidência interna do corpus (seção 15.4); zero violação de lane bloqueada; resposta monotônica dos controles contínuos declarados | deterministic permanece |
| G7 ONNX | suíte dourada dentro da tolerância declarada por saída, incluindo a sequência completa de decoding; e os sete limites da seção 16.4 respeitados em medição real, com destaque para `cpu_seconds <= 2,0` | não integrar modelo |
| G8 Produto | os seis gates de runtime já implementados em `lab.py` (`contract`, `fallback`, `reproducibility`, `quality`, `privacy_license`, `cost_latency`) passam contra os limiares de `gates.py`; e o loop candidatos/locks/reference/falhas/readback passa no Live | não promover `.ablx` |

Cada gate produz `stop`, `repeat`, `go limited` ou `go`. Nenhum gate autoriza automaticamente o seguinte; o proprietário aprova a próxima despesa. Os limiares numéricos que cada gate cita são congelados e versionados antes do run correspondente; alterar um limiar depois de ver o resultado invalida o gate e exige nova geração formal.

## 18. Decomposição futura de implementação

Esta especificação é grande demais para um único plano executável. Depois da revisão do usuário, serão escritos planos separados, nesta ordem:

1. **Training workspace e environment probe** — projeto PyTorch isolado, locks, diagnósticos, smoke e checkpoint resume.
2. **Auditoria de corpus e decisão de direitos** — reproduz e versiona as medições da seção 3.1.1, constrói o mapa auditado `collection → genre`, decompõe swing e jitter, e transforma a resposta a O1 em derivação verificável de `license_id`/`redistribution`. Não constrói dataset. É o único plano executável enquanto O1 estiver aberta.
3. **Spike de orçamento CPU/ONNX** — exporta um modelo **não treinado** com a forma alvo (small, 32×18, decoding iterativo de N passos), mede contra os sete limites da seção 16.4 e devolve o número máximo de passos de decoding viável dentro de `cpu_seconds <= 2,0`. Barato, e define a arquitetura antes de ela ser treinada.
4. **Dataset foundation V3** — schema de treino com `subhits`, canonical store, near-dedupe, cluster/split registry com guarda de componente gigante, shards e evidence packet.
5. **Baselines e avaliação** — retrieval/deterministic benchmark, GrooVAE, event AR, métricas e protocolo humano pré-registrado.
6. **Masked HVO Transformer** — tasks, losses, decoding, tiny/1%/10% bake-off.
7. **Full training e model card** — build 100%, run vencedor, blind test, anti-copy e decisão.
8. **ONNX provider** — export, equivalência, quantização, helper e orçamento, agora confirmando o spike do plano 3.
9. **Groove Brain product loop** — dashboard, prompt parser, candidates, locks, reference, mapping e Live readback.

A ordem mudou em relação à primeira versão por dois motivos concretos. A auditoria de dados e a decisão de direitos foram separadas da construção do dataset, porque O1 bloqueia a segunda e não a primeira. E o orçamento de CPU/ONNX foi movido para antes do treino: descobrir no antigo plano 6 que a arquitetura vencedora não cabe em `cpu_seconds <= 2,0` invalidaria os dois planos de treino anteriores.

Cada plano produz software testável e possui seu próprio stop condition. Nenhum plano de UI depende de um modelo ainda não promovido; usa baselines enquanto o treino evolui.

## 19. Riscos e respostas

1. **Corpus grande mas repetitivo:** near-dedupe, clusters e curva de escala; contar famílias, não arquivos.
2. **Weak labels ruins:** confiança, auditoria humana e `unknown`; categorias sem cobertura não aparecem.
3. **Microtiming artificial ou ausente:** auditar antes; não prometer humanize; GMD auxiliar separado.
4. **Memorização de processo anterior:** split por família, canaries, nearest-neighbor e blind test fechado.
5. **Transformer médio não caber/ganhar:** small primeiro; medium somente por curva de escala.
6. **AR melhor em rolls mas lento:** permitir arquitetura híbrida ou limitar AR a pós-processamento somente se o bake-off justificar.
7. **ONNX mudar resultado:** equivalência em logits, eventos e métricas antes de quantização.
8. **Dependências de treino contaminarem produto:** projetos/locks separados; usuário recebe somente runtime nativo.
9. **`.ablx` crescer demais:** CPU-first, modelo small, quantização após qualidade, budget de pacote antes de integração.
10. **Dirty prototypes confundirem baseline:** baseline é `HEAD` + digests promovidos; seed local de 500 e scripts hardcoded ficam fora.
11. **Métrica parecer boa e música ruim:** avaliação cega contra melhor baseline é gate, não demonstração opcional.
12. **Pesquisa virar projeto infinito:** cada degrau tem stop; produto determinístico continua útil se neural falhar.
13. **Origem do corpus não resolvida:** é o risco de maior severidade e bloqueia D1 em diante. A evidência da seção 2.1 contradiz a leitura de autoria original, e a marcação atual de direitos é uma constante de código, não uma derivação. Resposta: O1, e G1 reescrito para não poder passar por construção.
14. **Clustering colapsar em componente gigante:** near-duplicate contínuo não cria aresta de cluster por padrão; distribuição de tamanho publicada; maior componente abaixo de 5%.
15. **Grade densa perder rolls e flams por definição:** medido em 3,51% / 1,38% / 0,92% das notas em 16, 32 e 64 avos; canal `subhits` obrigatório e orçamento de perda declarado antes do build.
16. **Condições prometidas sem dados:** gênero, subgênero e techno não existem na taxonomia atual; entram só com mapa auditado e cobertura medida, ou não entram.
17. **Orçamento de CPU inviabilizar a arquitetura tarde demais:** `cpu_seconds <= 2,0` é teto de schema; spike de ONNX movido para antes do treino (plano 3).
18. **Dependência de SDK e host em beta:** o produto depende de `@ableton-extensions/sdk` `1.0.0-beta.0` e de um build beta do Live. A API pode mudar e o Gate 0 só prova o comportamento do host testado. Resposta: registrar build do Live e versão do host em cada evidência, e não escrever plano de produto que assuma estabilidade de API.
19. **Licença do Extensions SDK versus repositório público:** a licença do SDK proíbe distribuir o SDK ou partes dele fora da aplicação, e trata material pré-lançamento como confidencial. Os arquivos `AbletonMCPServer_Extension/vendor/ableton-extensions-{sdk,cli}-1.0.0-beta.0.tgz` estão versionados em um repositório público MIT. Isso é independente do treino e precisa de decisão do proprietário antes de qualquer publicação nova. Registrado aqui porque os planos 8 e 9 dependem de empacotar `.ablx`.

## 20. Decisões finais

- Groove Brain é bateria/ritmo, não Music Brain geral.
- A declaração de origem do proprietário está registrada, e a evidência medida na seção 2.1 não a sustenta na forma “os arquivos são meus e podem ser redistribuídos”. A pergunta bloqueante O1 decide o tratamento; até lá o programa não passa de D0.
- O seed V2 de 1.685 itens é baseline de retrieval; não é o dataset de treino completo.
- O corpus completo precisa de near-dedupe, famílias e splits antes de qualquer treino sério.
- HVO + envelope lossless é a representação principal; event-based é challenger e proteção contra perda de rolls/flams.
- Masked Transformer é challenger recomendado, não vencedor pré-declarado.
- GrooVAE e event AR são baselines neurais obrigatórios.
- Humanize só é aprendido se os dados provarem expressão útil.
- PyTorch/CUDA são exclusivos do laboratório; produto usa ONNX/runtime nativo local.
- CPU é caminho universal; aceleração é opcional.
- Modelo precisa vencer retrieval/deterministic em avaliação cega e anti-copy.
- Nenhum treino full, integração neural, push, lançamento ou publicação é autorizado por esta especificação.

## 21. Fontes primárias

- [GrooVAE — Learning to Groove with Inverse Sequence Transformations](https://proceedings.mlr.press/v97/gillick19a.html)
- [Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove)
- [Magenta MusicVAE/GrooVAE training reference](https://github.com/magenta/magenta/tree/main/magenta/models/music_vae)
- [GrooveTransformer source and HVO documentation](https://github.com/behzadhaki/GrooveTransformer)
- [Transformer Groove Infilling project and source](https://transformergrooveinfilling.github.io/)
- [PocketVAE](https://arxiv.org/abs/2107.05009)
- [Conditional Drums Generation using Compound Word Representations](https://arxiv.org/abs/2202.04464)
- [PyTorch 2.12 release and Blackwell/CUDA matrix](https://pytorch.org/blog/pytorch-2-12-release-blog/)
- [ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [ONNX Runtime model optimizations](https://onnxruntime.ai/docs/performance/model-optimizations/)
- [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
- [microsoft/DirectML — aviso de manutenção](https://github.com/microsoft/DirectML)
- [DirectML — introdução (Microsoft Learn)](https://learn.microsoft.com/en-us/windows/ai/directml/dml)

Notas de verificação, feitas em 2026-08-31:

- os links acima foram abertos e conferidos; título e autoria de GrooVAE, PocketVAE e Conditional Drums Generation batem;
- o repositório `magenta/magenta` está **arquivado** desde 2026-01-06 e é somente leitura;
- a afirmação sobre estado de manutenção do DirectML e sobre Windows ML **não** está na página de execution providers do ONNX Runtime; a fonte primária é o repositório `microsoft/DirectML`. A citação foi corrigida.

## 22. Critério de aprovação desta especificação

O documento está pronto para virar planos de implementação quando o usuário confirmar:

1. o escopo exclusivo de bateria/ritmo;
2. **a resposta à pergunta bloqueante O1 da seção 2.1**, escolhendo entre (a), (b) e (c). Sem ela, apenas os planos 1, 2 e 3 podem ser escritos;
3. a comparação A/B/C em vez de treinar um modelo grande diretamente;
4. o dataset/split/anti-copy antes do full run;
5. a promoção somente após avaliação cega, com o número `≥21/30` da seção 15.5 aceito antes da coleta;
6. a separação laboratório PyTorch versus produto ONNX `.ablx`;
7. a decomposição em nove planos independentes, com auditoria de corpus e spike de CPU/ONNX antes do dataset e do treino;
8. quem avalia no teste cego e quantas pessoas são, já que isso limita o que o model card pode afirmar;
9. o que fazer com os `.tgz` do Extensions SDK versionados no repositório público (risco 19), já que os planos 8 e 9 dependem de empacotar `.ablx`.
