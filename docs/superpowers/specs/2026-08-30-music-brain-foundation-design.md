# Music Brain — arquitetura fundacional de modelo musical MIDI

- **Status:** visão geral preservada para referência; o escopo atual foi reduzido a bateria/ritmo e dados/treinamento de Groove Brain são regidos por [Groove Brain — dataset e treinamento neural](2026-08-31-groove-brain-dataset-training-design.md); código e treinamento não autorizados
- **Data:** 2026-08-30
- **Projeto:** `ableton-mcp-server`
- **Horizonte:** protótipo de pesquisa com caminho comercial; nenhum lançamento nesta fase
- **Documento relacionado:** [Groove Brain Extension](2026-08-30-groove-brain-extension-design.md)

## 1. Decisão em uma frase

Music Brain será um sistema híbrido de composição MIDI: fundação de dados com proveniência, modelo especializado de groove, Transformer simbólico para composição e edição multitrack, planner que converte intenção e contexto do Ableton em uma especificação musical, verifier que bloqueia resultados inválidos ou excessivamente parecidos com o treino, e uma camada de integração que só altera o Live após aprovação explícita do usuário.

## 2. Resultado da pesquisa

O código atual não é um LLM treinado. Ele é um baseline determinístico: recebe seed e controles, gera bateria/baixo por regras e monta um plano simples de produção. Isso é útil como comparação, fallback e teste de integração, mas não aprende o corpus e não compõe música longa com coerência.

O diretório local inspecionado também não é um corpus de canções completas. Evidência medida:

- 183.429 arquivos `.mid`/`.midi`, aproximadamente 100 MB;
- 172.133 conteúdos SHA-256 únicos;
- 11.296 duplicatas exatas, cerca de 6,16% dos arquivos;
- amostra aleatória: mediana de uma track, 33 notas e oito beats;
- predominância de loops curtos de bateria, inclusive arquivos que usam canal MIDI 1 em vez do canal 10.

Conclusão: esse material tem perfil útil para Groove Brain, não cobertura suficiente para Composer Brain multitrack. O proprietário esclareceu depois desta pesquisa que os padrões foram gerados/exportados por processo próprio, pertencem a ele e estão autorizados para o projeto; nomes de produtos na hierarquia não identificam titularidade dos arquivos.

**Decisão revisada:** o corpus é registrado como `source_kind=author`, `license_id=user-owned` e `redistribution=full`, com a declaração do proprietário como evidência raiz. Isso substitui a quarentena interna anterior, sem inventar certificação jurídica externa. Dataset neural ainda depende de near-dedupe, famílias, splits e gates da especificação canônica de 2026-08-31.

## 3. Problema de produto

Geradores MIDI comuns tendem a entregar uma sequência isolada. O produtor ainda precisa traduzir intenção, respeitar o Set, escolher instrumentos, preservar partes boas, corrigir harmonia, organizar seções e aplicar o resultado com segurança.

Music Brain deve resolver edição musical dentro do fluxo:

1. compreender contexto musical disponível no Live;
2. converter pedido em estrutura explícita e editável;
3. gerar continuação, acompanhamento, variação ou infill;
4. preservar tracks, regiões e eventos bloqueados;
5. oferecer candidatos comparáveis;
6. explicar controles e origem do resultado;
7. aplicar somente após confirmação e validar o que foi escrito.

O diferencial defendível não é “texto vira MIDI”. Ableton Live 12 já oferece geradores e transformações MIDI; produtos como Aether e Staccato já anunciam geração por texto e edição. Diferencial deve ser combinação de contexto do Set, controles por papel musical, infill seletivo, funcionamento local, proveniência auditável, prevenção de cópia e writeback seguro.

## 4. Alternativas consideradas

### 4.1 Um único modelo universal desde o início — rejeitado para V1

Um modelo único de bateria, harmonia, melodia, arranjo e linguagem parece elegante, mas exige corpus muito mais diverso, contexto longo, mais GPU e avaliação difícil. Erro em um domínio contamina todo sistema. Fica como hipótese futura depois dos modelos especializados provarem valor.

### 4.2 Somente Groove Brain — útil, mas insuficiente como visão

É o primeiro domínio treinável e o caminho mais curto até qualidade percebida. Não satisfaz objetivo original de compor e editar músicas multitrack. Permanece como produto vertical e componente do sistema maior.

### 4.3 Sistema híbrido especializado — escolhido

Separar dados, groove, composição, planejamento, verificação e integração reduz acoplamento. Cada parte possui baseline, conjunto de testes e gate próprios. Modelos podem evoluir sem quebrar contrato com Ableton.

## 5. Arquitetura escolhida

```text
pedido + SessionSnapshot
          |
          v
      Music Planner --------> MusicSpec estruturado
          |                          |
          |                          +--> Groove Brain
          |                          +--> Composer Brain
          |                          +--> Retrieval/transformações
          |                                   |
          +-----------------------------------+
                                              v
                                      candidatos MIDI
                                              |
                                              v
                                      Music Verifier
                               validade | controles | cópia
                                              |
                                              v
                                     preview + comparação
                                              |
                                      aprovação humana
                                              |
                                              v
                                  Ableton Writer + readback
```

Cinco fronteiras permanentes:

1. **Music Data Foundation:** direitos, inventário, parser, representação canônica, dedupe, splits e artefatos versionados.
2. **Groove Brain:** bateria, microtiming, velocity, fills, variações e regeneração por lane.
3. **Composer Brain:** harmonia, melodia, baixo, acompanhamento, estrutura local e edição multitrack.
4. **Planner + Verifier:** intenção estruturada, restrições, roteamento, validade, aderência, originalidade e ranking.
5. **Runtime + Ableton Adapter:** serviço local, cache, cancelamento, preview, aplicação segura e diagnóstico.

Nenhum componente conhece detalhes internos dos outros. Comunicação usa contratos versionados e dados serializáveis. Modelo falhar não pode corromper Set; integração falhar não pode modificar modelo ou dataset.

## 6. Contratos centrais

### 6.1 `SessionSnapshot`

Leitura imutável e efêmera do contexto necessário:

- tempo, compasso, posição e range musical;
- tracks selecionadas e papéis inferidos com confiança;
- instrumentos, programas, Drum Rack ou perfil explícito;
- notas, automações MIDI relevantes e regiões bloqueadas;
- tonalidade e acordes nativos quando disponíveis;
- IDs de sessão apenas para readback, nunca como identidade persistente.

### 6.2 `MusicSpec`

Plano musical editável antes da geração:

- tarefa: `generate`, `continue`, `infill`, `accompany`, `vary`, `humanize` ou `arrange`;
- duração, seções, tempo, compasso e tonalidade;
- tracks e papéis: drums, bass, harmony, melody, texture e control;
- densidade, energia, polifonia, registro, groove e novidade;
- eventos, lanes, tracks e regiões bloqueados;
- referência musical opcional;
- seed, quantidade de candidatos e orçamento de inferência;
- origem e confiança de cada metadado inferido.

Planner pode começar determinístico. Um pequeno modelo de linguagem local só entra depois se melhorar tradução de texto para `MusicSpec`; ele não substitui modelo musical.

### 6.3 `GenerationCandidate`

Cada candidato carrega:

- eventos MIDI canônicos;
- seed, modelo, tokenizer e dataset versionados;
- controles pedidos e medidos;
- warnings e violações;
- vizinhos mais próximos no treino e escores de similaridade;
- tempo de geração;
- hash canônico para reprodução e auditoria.

### 6.4 `ApplyReceipt`

Aplicação registra alvo resolvido, precondições, conteúdo pretendido, conteúdo relido, alterações observadas e falha parcial. Mutação ambígua nunca é repetida automaticamente. `run_batch` continua sendo undo agrupado, não transação com rollback.

## 7. Fundação de dados

### 7.1 Política de direitos

Cada item precisa de `rights_record` com:

- identidade estável da fonte;
- titular ou origem;
- licença e versão;
- evidência armazenada;
- permissão para processamento, ML, pesos derivados e distribuição;
- restrições comerciais, territoriais e de atribuição;
- estado `allowed`, `research_only`, `quarantined` ou `rejected`;
- data e responsável pela decisão.

Pipeline falha fechado. Pasta “comprada” ou “royalty-free” não vira `allowed` sem evidência que cubra o uso. Para material criado pelo próprio usuário, uma declaração autoral versionada e ligada aos hashes é a evidência de projeto exigida; fontes de terceiros continuam sujeitas à licença correspondente.

### 7.2 Fontes aceitáveis

Ordem preferida:

1. MIDI composto ou performado pelo usuário, com cadeia autoral documentada;
2. encomendas de músicos com licença explícita para ML, derivados e pesos comerciais;
3. programa opt-in para criadores, com remuneração e opção de retirada aplicável somente a versões futuras;
4. domínio público e CC0 auditados por obra e jurisdição;
5. datasets acadêmicos apenas quando licença cobre uso pretendido; dados `non-commercial` ficam em ambiente de pesquisa separado.

Composer Brain precisa de canções multitrack, não apenas loops. Meta de aquisição deve ser expressa em horas, obras, gêneros, instrumentações, comprimentos e diversidade de autores, não somente número de arquivos.

### 7.3 Representação canônica

Armazenamento usa IR MIDI lossless ou explicitamente loss-accounted:

- PPQ/ticks originais;
- tempo, time signature e key signature;
- note on/off, velocity e channel;
- program change, pedal, pitch bend e CC relevantes;
- nomes de track quando permitidos;
- origem de tonalidade/acorde: `native`, `estimated` ou `defaulted`;
- papel do instrumento, regra usada e confiança;
- hash bruto, hash canônico e cluster de near-duplicate.

Modelo nunca lê arquivos diretamente. Tokenização é uma projeção versionada do IR. Assim, trocar vocabulário não obriga reprocessar ou destruir fonte.

### 7.4 Qualidade, dedupe e splits

Três níveis de deduplicação:

1. bytes exatos;
2. eventos canônicos equivalentes após remover metadados irrelevantes;
3. versões próximas por fingerprints de ritmo, pitch, estrutura e alinhamento temporal.

Split ocorre por obra, cluster e fonte antes de segmentar. Nenhum fragmento, transposição ou versão da mesma obra atravessa train/validation/test. Tokenizer e BPE são treinados somente no train. Test cego fica congelado e inacessível ao retriever usado em produção.

## 8. Tokenização

### 8.1 Composer Brain

Ponto de partida: REMI+ multitrack, sequencial por barra e track, implementado sobre MidiTok ou camada equivalente auditada. Vocabulário inclui barra, posição, duração, pitch, velocity, programa/papel, tempo, compasso, controles e tokens de máscara. BPE treinado no split de treino reduz comprimento sem apagar semântica.

Razões:

- representação event-based preserva estrutura musical melhor que texto ABC para produção MIDI;
- barras e tracks tornam infill e acompanhamento naturais;
- ecossistema MidiTok permite comparar REMI+, MIDILike, CPWord, Octuple e MMM com mesma base;
- vocabulário musical próprio evita depender de tokenizer de linguagem.

### 8.2 Groove Brain

Groove exige resolução expressiva maior. Projeção HVO ou eventos com delta fino preserva hit, velocity e microtiming. Lane canônica fica separada do pitch final do plugin. O envelope lossless continua disponível para round-trip e exportação.

### 8.3 Bake-off obrigatório

Antes do modelo completo, comparar REMI+, MIDILike e uma representação composta. Critérios:

- tokens por beat e por barra;
- truncamento em 8k e 16k tokens;
- fidelidade de round-trip;
- cobertura de expressão;
- facilidade de grammar masking;
- throughput e VRAM;
- qualidade de um mesmo tiny model e orçamento.

Escolha é feita por evidência, não preferência estética.

## 9. Estratégia de modelos

### 9.1 Baselines permanentes

- geradores determinísticos atuais;
- transformações musicais controladas;
- retrieval por metadados e similaridade;
- n-gram ou Transformer minúsculo para validar pipeline.

Produto sempre mantém fallback útil. Modelo neural precisa vencer melhor baseline, não apenas produzir arquivos válidos.

### 9.2 Groove Brain V1

- modelo especializado de aproximadamente 20–50 milhões de parâmetros;
- contexto de loops e pequenas frases;
- tarefas causal, masked infill, fill, variação, lane regeneration e humanize;
- controles de densidade, energia, swing, complexidade, lane e distância da referência;
- inferência local e exportável para runtime isolado.

Tamanho final depende de dados permitidos e curva de escala. Arquitetura maior não compensa corpus estreito ou repetitivo.

### 9.3 Composer Brain V1

- Transformer decoder-only MIDI-native, alvo inicial de 50–150 milhões de parâmetros;
- RoPE, RMSNorm, SwiGLU, mixed precision, gradient checkpointing e atenção eficiente suportada;
- contexto de 8k tokens como mínimo experimental e 16k como alvo condicionado a memória;
- treino multitarefa: causal generation, span/bar/track infill, continuation, accompaniment e control tokens;
- grammar mask durante decoding;
- amostragem com temperature, top-p, repetition controls e restrições por track.

Primeira versão não promete canções inteiras de vários minutos em uma única passagem. Gera e edita janelas coerentes; planner organiza seções e reaproveita motivos. Modelo hierárquico de estrutura longa entra somente se V1 atingir gates locais.

### 9.4 Referências operacionais

- [MIDI-GPT](https://github.com/Metacreation-Lab/MIDI-GPT) demonstra decoder multitrack com infill e controles; serve como baseline arquitetural. Código é MIT, mas [pesos publicados](https://huggingface.co/Metacreation/MIDI-GPT) são CC BY-NC 4.0 e não entram em produto comercial.
- [Anticipatory Music Transformer](https://github.com/jthickstun/anticipation) demonstra condicionamento no futuro e checkpoints maiores; custo publicado mostra por que escala precisa vir depois do pipeline.
- [FIGARO](https://github.com/dvruette/figaro) demonstra condicionamento por descrição e estrutura em encoder-decoder.
- [Museformer](https://github.com/microsoft/muzic/tree/main/museformer) demonstra atenção hierárquica para sequências longas, mas seu stack não é ponto de partida da V1.
- [MidiTok](https://github.com/Natooz/MidiTok) fornece base prática para bake-off de tokenização.

Pesos externos são baseline de laboratório apenas quando licença permite. Modelo de produto começa de inicialização própria ou checkpoint com direitos comerciais completos e vocabulário compatível. LoRA pode servir a personalização posterior; não é estratégia primária para trocar vocabulário e objetivo.

## 10. Treinamento

### 10.1 Ambientes

- **Preparação e inferência:** Windows local, reutilizando parser e contratos do repositório.
- **Treinamento:** Linux reproduzível, PyTorch com CUDA validado para a GPU escolhida.
- **Artefatos:** dataset, tokenizer, config, checkpoint, métricas, model card e hashes versionados fora do Git.
- **Segredos:** nenhum token ou credencial em config versionada.

PyTorch 2.7 introduziu suporte oficial a Blackwell com CUDA 12.8, relevante para a RTX 5070; a matriz exata deve ser congelada por experimento conforme [anúncio oficial](https://pytorch.org/blog/pytorch-2-7/).

### 10.2 Capacidade local

Máquina medida: RTX 5070 com cerca de 12 GB VRAM, aproximadamente 64 GB RAM e i9-12900KS. Boa para parsing, tokenização, tiny models, ablations, inferência, quantização e possivelmente treino completo do Groove Brain com batches pequenos. Composer Brain de 50–150M pode rodar localmente com checkpointing e acumulação, mas iteração será lenta e contexto longo reduzirá batch.

Treino sério do Composer Brain deve prever GPU de nuvem com 40–80 GB. Compra de horas só ocorre depois de estimar tokens, throughput e curva de perda em runs locais. Não existe orçamento honesto antes dessa medição.

### 10.3 Escada de treino

1. **Pipeline unitário:** round-trip, tokenizer, packing, loss mask e split em fixtures sintéticas.
2. **Overfit controlado:** poucas sequências; modelo deve memorizar deliberadamente para provar fluxo.
3. **Tiny run:** pequena amostra rights-cleared; validar queda de loss, geração e checkpoints.
4. **Ablation run:** comparar tokenizer, contexto, tarefas e controles sob mesmo orçamento.
5. **Pilot run:** cerca de 10% do train, sem tocar test cego.
6. **Full run:** corpus permitido completo, configuração congelada e checkpoints periódicos.
7. **Control/infill tune:** mistura calibrada de tarefas e hard examples.
8. **Runtime optimization:** quantização, distillation ou ONNX somente após qualidade aprovada.

Cada degrau pode parar o seguinte. Falha de dados não é corrigida aumentando modelo.

## 11. Avaliação e gates

### Gate A — direitos e lineage

- 100% dos itens de treino possuem `rights_record=allowed`;
- zero item sem declaração autoral ou licença compatível em dataset, tokenizer, retriever, checkpoint e benchmark;
- hashes e origem permitem reconstruir inclusão de cada item;
- versões `research_only` nunca alimentam artefato comercial.

### Gate B — integridade de dados

- todo descarte tem reason code reproduzível;
- zero duplicata exata ou cluster conhecido atravessa splits;
- amostra de near-duplicate auditada;
- parse/serialize preserva eventos declarados pela política de fidelidade;
- truncamento e descarte não escondem um gênero, autor ou instrumento.

### Gate C — tokenizer

- round-trip válido em suíte congelada;
- métricas de comprimento e truncamento publicadas;
- BPE treinado somente no train;
- tokens desconhecidos e eventos sem suporte falham explicitamente.

### Gate D — modelo musical

- 100% dos outputs aceitos passam parser e grammar checks;
- controles contínuos apresentam resposta monotônica no benchmark definido;
- regiões e tracks bloqueadas permanecem bit-identical no IR canônico;
- nearest-neighbor e testes de extração não indicam cópia inaceitável;
- avaliação cega supera melhor baseline com limite inferior do intervalo de confiança acima de 50%;
- métricas MusPy e métricas próprias não mostram colapso de pitch, ritmo, silêncio ou repetição.

### Gate E — produto

- geração cancelável e sem helper órfão;
- P50/P95 medidos em cold/warm start no hardware-alvo;
- zero overwrite não autorizado;
- todo sucesso de escrita passa readback;
- falha de modelo, timeout ou bridge produz diagnóstico e mantém Set preservado;
- pelo menos 500 operações end-to-end com falhas injetadas antes de promoção.

Thresholds musicais e de similaridade são congelados antes de abrir test cego. Métrica ajustada após ver resultado invalida rodada.

## 12. Originalidade e prevenção de memorização

Defesa em camadas:

1. dedupe/near-dedupe antes do split;
2. holdout por obra e fonte;
3. treinamento sem retriever sobre test;
4. busca de vizinho no treino para cada candidato;
5. comparação por eventos canônicos, fingerprints rítmicos, contorno melódico e transposição;
6. rejeição ou regeneração acima de limiar congelado;
7. canary sequences sintéticas para testar extração;
8. model card com limitações e casos conhecidos.

Originalidade não é distância aleatória: uma progressão comum ou padrão básico pode ser legítimo. Gate combina similaridade, comprimento, raridade e revisão humana.

## 13. Serving e integração com Ableton

Runtime de inferência fica fora da UI e fora da thread do Live. Processo isolado possui health check, versão, limites de memória, timeout, cancelamento, fila limitada e encerramento ligado ao processo pai. Interface de provider já existente em Groove Intelligence pode ser generalizada; o modelo não é importado diretamente por `server.py`.

Fluxo:

1. adapter captura `SessionSnapshot`;
2. planner produz `MusicSpec` visível;
3. provider gera candidatos sem tocar Live;
4. verifier filtra e explica;
5. usuário escolhe candidato e destino;
6. writer revalida alvo e aplica uma vez;
7. readback produz `ApplyReceipt`.

MCP Server continua útil como laboratório e interface agentic. Produto Groove Brain pode seguir a especificação `.ablx`; Composer Brain não fica preso a essa embalagem antes de Gate 0 provar helper e tamanho.

## 14. O que reaproveitar e o que isolar

### Reaproveitar

- parser/serializer MIDI lossless;
- schema, provenance, rights e artifact manifests de Groove Intelligence;
- provider boundary e subprocess wrapper;
- resource limits, gates, evidence e promotion;
- safe apply/readback do bridge;
- geradores determinísticos como baseline;
- três tools públicas de Music Brain como contratos experimentais, não como arquitetura final.

### Isolar ou substituir

- branch `wip/music-brain`: não fazer merge em bloco; extrair somente ideias cobertas por testes e spec;
- `journeys.py` e registro local `plan_user_journey`: protótipo quebrado, fora do núcleo;
- UDP realtime server: contradiz decisão anterior de transporte e não possui contrato seguro;
- script de ingestão privado: caminho hardcoded e análise de microtiming incompleta;
- seed V2 promovido: preservar como baseline de retrieval, não confundir com dataset neural;
- alterações locais de swing/polyrhythm: só entram se ganharem testes e papel claro no baseline.

“Centralizar em main” não significa misturar tudo. Processo futuro: preservar snapshot, classificar cada diff como salvage/archive/discard, testar salvage, commitar unidades coerentes, e somente então remover branches/worktrees com autorização explícita. Nenhum protótipo quebrado entra em `main` para produzir aparência de limpeza.

## 15. Programa de implementação decomposto

Projeto é grande demais para um plano monolítico. Cada workstream recebe spec/plan e gate próprios.

### Workstream 0 — estabilização e proveniência

- mapear alterações locais e branches;
- proteger ou arquivar trabalho recuperável;
- remover registro quebrado sem perder fonte;
- registrar a declaração autoral e isolar somente artefatos sem provenance suficiente;
- restaurar testes e inventário coerentes;
- deixar `main` como fonte única sem publicar.

### Workstream 1 — Music Data Foundation

- rights manifest e fail-closed ingestion;
- IR canônico;
- parser adapters;
- dedupe, near-dedupe e lineage;
- split registry;
- dataset build e evidence packet.

### Workstream 2 — tokenizer e baselines

- bake-off reprodutível;
- deterministic/retrieval baselines;
- tiny model harness;
- métricas e benchmark congelados.

### Workstream 3 — Groove Brain neural

- corpus permitido de groove;
- treino especializado;
- infill/variation/humanize;
- provider otimizado;
- gate contra baseline.

### Workstream 4 — Composer Brain V1

- corpus multitrack permitido;
- decoder-only 50–150M;
- causal/infill/accompaniment;
- controles e grammar mask;
- long-context evaluation.

### Workstream 5 — Planner, Verifier e runtime

- `SessionSnapshot`, `MusicSpec`, candidates e receipts;
- roteamento entre retrieval, groove e composer;
- originalidade, ranking e diagnósticos;
- serviço local e cache.

### Workstream 6 — Ableton product loop

- preview e comparação;
- locks e regeneração seletiva;
- safe apply/readback;
- UX contextual;
- performance e falhas injetadas.

Ordem crítica: 0 → 1 → 2. Workstream 3 começa após dados de groove; Workstream 4 só começa quando houver corpus multitrack suficiente. Workstreams 5 e 6 usam baselines antes de depender do modelo grande.

## 16. Primeiro corte executável recomendado

Após aprovação desta spec, primeiro plano não treina modelo. Ele cobre Workstream 0 e início do 1:

1. consolidar repositório sem perder trabalho;
2. registrar a declaração autoral do corpus e preservar hashes/origem;
3. definir `rights_record`, `SourceManifest` e políticas fail-closed para fontes futuras;
4. criar fixtures sintéticas e próprias mínimas;
5. provar ingestão, IR, dedupe e split com testes;
6. gerar primeiro evidence packet rights-cleared.

Saída é pequena, testável e necessária para qualquer treino legítimo. Ao fim, já existe fundação capaz de receber novos corpora sem reescrever pipeline.

## 17. Riscos e respostas

1. **Corpus autoral repetitivo:** começar por Groove Brain, medir famílias e curva de escala; não confundir contagem de arquivos com diversidade.
2. **Dados multitrack fracos:** Composer Brain fica bloqueado; produto de groove/retrieval continua útil.
3. **Memorização:** splits por obra, near-dedupe, canaries e verifier.
4. **Custo de GPU:** estimar tokens/throughput local antes de alugar; usar escala progressiva.
5. **Latência local:** modelos menores, quantização e cache depois do gate de qualidade.
6. **SDK beta:** adapter isolado e Gate 0 da extensão.
7. **Escopo explodir:** workstreams independentes e stop/go por evidência.
8. **Protótipos contaminarem main:** nenhum merge em bloco; salvage por diff e testes.
9. **Licença de pesos externos:** modelos e checkpoints ficam segregados por finalidade; `non-commercial` nunca entra em produto.
10. **Qualidade parecer boa só por métrica:** blind A/B com músicos e tarefas reais no Ableton.

## 18. Critério de sucesso do programa

Music Brain alcança primeira prova forte quando:

- dataset de treino tem direitos e lineage completos;
- modelo próprio vence baselines em avaliação cega;
- usuário controla região, papel, densidade, groove e novidade;
- infill preserva material bloqueado;
- verifier barra inválidos e cópias prováveis;
- geração roda localmente dentro do orçamento medido;
- aplicação no Live é explícita, única e confirmada por readback;
- qualquer resultado pode ser reproduzido por versões, seed e hash.

## 19. Decisões finais

- Arquitetura híbrida, não um LLM universal na V1.
- Groove Brain e Composer Brain são modelos separados com contratos comuns.
- Composer Brain usa MIDI tokenizado, não ABC, como representação principal.
- REMI+ é baseline de tokenização, sujeito a bake-off.
- Treino principal é próprio; pesos não comerciais servem somente a pesquisa permitida.
- O corpus atual é tratado como autoral conforme declaração explícita do proprietário; fontes futuras continuam fail-closed.
- Planner começa estruturado/determinístico; LLM de texto é opcional e periférico.
- Verifier e originalidade fazem parte do núcleo, não acabamento.
- Integração Ableton nunca permite ao modelo escrever diretamente.
- Primeiro trabalho após aprovação é estabilização + fundação de dados, não treino pesado.
- Nenhum lançamento, push ou publicação está autorizado por esta especificação.

## 20. Fontes principais

- [MIDI-GPT paper](https://arxiv.org/abs/2501.17011) e [repositório](https://github.com/Metacreation-Lab/MIDI-GPT)
- [Anticipatory Music Transformer paper](https://arxiv.org/abs/2306.08620) e [repositório](https://github.com/jthickstun/anticipation)
- [FIGARO paper](https://arxiv.org/html/2201.10936) e [repositório](https://github.com/dvruette/figaro)
- [Museformer paper](https://arxiv.org/html/2210.10349) e [repositório](https://github.com/microsoft/muzic/tree/main/museformer)
- [MidiTok paper](https://arxiv.org/abs/2310.17202) e [repositório](https://github.com/Natooz/MidiTok)
- [Lakh MIDI Dataset](https://colinraffel.com/projects/lmd/)
- [Lakh deduplication study and artifacts](https://zenodo.org/records/17811316)
- [MAESTRO dataset](https://magenta.tensorflow.org/datasets/maestro)
- [MusPy](https://github.com/salu133445/muspy)
- [Ableton Live 12 MIDI Tools](https://www.ableton.com/en/live-manual/12/midi-tools/)
- [Ableton Extensions SDK](https://www.ableton.com/en/live/extensions/)
- [PyTorch 2.7 / Blackwell support](https://pytorch.org/blog/pytorch-2-7/)
- [U.S. Copyright Office — Generative AI Training](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
