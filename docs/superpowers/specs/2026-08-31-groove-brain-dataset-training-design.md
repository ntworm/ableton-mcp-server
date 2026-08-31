# Groove Brain — design canônico de dataset e treinamento neural

- **Status:** direção aprovada em conversa; especificação escrita aguardando revisão do usuário
- **Data:** 2026-08-31
- **Projeto:** `ableton-mcp-server`
- **Escopo:** bateria e ritmo MIDI; nenhum Composer Brain, lançamento ou publicação
- **Autoria do corpus:** declarada pelo proprietário como material próprio, autorizado para uso no projeto
- **Documento de produto relacionado:** [Groove Brain Extension](2026-08-30-groove-brain-extension-design.md)

## 1. Decisão em uma frase

Groove Brain será treinado como um sistema rítmico híbrido: o corpus autoral passa por canonicalização lossless, deduplicação exata/canônica/próxima e splits por família; três modelos são comparados sob o mesmo orçamento; um Transformer HVO condicional e mascarado é o challenger principal, mas só avança se vencer retrieval, transformações determinísticas, GrooVAE e um decoder event-based em qualidade cega, originalidade e custo local; o vencedor é exportado para ONNX e executado offline por um helper isolado da Extension.

## 2. Correções e precedência

Este documento é a fonte de verdade para **dados e treinamento neural do Groove Brain**. Ele substitui, somente nesse domínio:

- as seções 13–17 de `2026-08-30-groove-brain-extension-design.md` quando houver conflito;
- as decisões gerais de Music Brain sobre Composer Brain, REMI+ e composição multitrack;
- a premissa antiga de que os arquivos eram componentes licenciados da Toontrack.

O usuário esclareceu que os padrões MIDI foram gerados/exportados por processo próprio, pertencem a ele e estão autorizados para este trabalho. Nomes como Toontrack, EZX, Superior Drummer e SSD na hierarquia descrevem referências de organização e compatibilidade, não titularidade dos arquivos. O pipeline registra essa declaração como evidência de origem do projeto; não inventa certificação jurídica independente.

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

O inventário preservado registra:

- `183.429` arquivos descobertos e processados;
- `180.614` MIDIs válidos;
- `2.815` falhas de parser com reason code;
- `11.296` repetições por digest bruto;
- aproximadamente 100 MB de MIDI bruto;
- predominância de loops curtos de bateria;
- rótulos úteis, porém fracos, na hierarquia de diretórios.

O seed de retrieval passou por duas gerações:

- V1: `2.048` representantes em `groove.index.v1`;
- V2 canônico no `HEAD`: `1.685` representantes em `groove.index.v2` após a mudança de representação/taxonomia.

Existe uma experiência local não commitada com seed de `500` itens. Ela não é baseline, dataset de treino nem artefato promovido.

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
- harness de experimento e comparação;
- modelo treinado ou promovido;
- export ONNX validado;
- inferência neural dentro do helper `.ablx`;
- dashboard final do Groove Brain.

O `NeuralSubprocessProvider` atual é uma fronteira de segurança, não uma IA treinada. O código antigo de `music_brain` e o branch `wip/music-brain` são heurísticos e permanecem apenas como baselines ou material de descarte seletivo.

## 4. Objetivo mensurável da V1 neural

O primeiro modelo deve gerar e editar grooves curtos de bateria que:

1. respeitem estilo/subgênero, BPM, compasso, função, densidade, energia, swing, complexidade e lanes bloqueadas;
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

**Riscos:** células densas podem esconder rolls/flams; geração totalmente mascarada exige decoding calibrado; probabilidades de hit podem colapsar para padrões médios.

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
corpus MIDI autoral (read-only)
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
- `source_kind=author`;
- `license_id=user-owned`;
- evidência da declaração de autoria/autorização;
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

Baseline inicial: duas barras em 4/4, 32 passos de semicolcheia, offset contínuo. Challenger de 64 passos entra se reduzir perda relevante. Nenhum evento é silenciosamente fundido: subeventos ficam no envelope e alimentam o decoder event-based; o HVO registra colisão e só entra no treino se a política da versão declarar sua representação.

Outros compassos são preservados no IR e avaliados separadamente. Eles só entram no modelo V1 se houver cobertura mínima por split; caso contrário permanecem no retrieval e são explicitamente fora de distribuição para geração neural.

### 8.3 Tensores

Os shards HVO armazenam separadamente:

- `hit`: booleano/uint8 `[example, time, lane]`;
- `velocity`: float normalizado, com loss mask por hit;
- `offset`: deslocamento normalizado pela célula, com loss mask por hit;
- `observed_mask`: posições fornecidas ao modelo;
- `target_mask`: posições cobradas pela tarefa;
- condições categóricas e contínuas;
- IDs opacos de exemplo, família e origem.

Shards event-based armazenam tokens/atributos equivalentes e apontam para o mesmo exemplo canônico. O formato físico é sharded e content-addressed, com arrays NumPy mmap-friendly e índice JSONL canônico; nenhum pickle é aceito.

### 8.4 Janela

Unidade primária: duas barras. Arquivos maiores geram janelas com sobreposição somente depois de o split por família ser definido. Janelas do mesmo arquivo ou família nunca atravessam splits. Fills podem usar uma barra de contexto + região-alvo final; continuação curta usa contexto anterior explícito.

## 9. Dedupe, famílias e splits

### 9.1 Camadas de deduplicação

1. bytes idênticos;
2. eventos equivalentes após remover metadados irrelevantes;
3. equivalência rítmica por lanes, ignorando mapping de pitch;
4. near-duplicate por distância HVO/grammar/features;
5. família por hierarquia, lineage do gerador anterior e assinaturas de geração.

Thresholds de near-duplicate são calibrados com pares exatos, variações conhecidas e pares musicais diferentes. Eles são congelados antes de abrir o blind test.

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

## 10. Labels e condições

### 10.1 Weak labels

Nomes de diretório fornecem sinais de genre, subgenre, style, section, feel e BPM, mas não verdade absoluta. Cada label carrega origem e confiança. Aliases passam pela taxonomia V2; categorias raras ou ambíguas viram `unknown`/hierarquia genérica em vez de rótulo inventado.

Um conjunto auditado manualmente mede precisão dos labels mais importantes, especialmente techno, dark techno, fills e seções. O dashboard só oferece condição cujo train split possui cobertura e qualidade mínimas.

### 10.2 Condições do modelo

- gênero/subgênero/estilo;
- BPM normalizado;
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

“Techno sombrio 128 BPM” passa primeiro por parser local determinístico e produz uma `GrooveSpec` visível. Sinônimos multilíngues mapeiam para taxonomia e controles. Nenhum LLM é necessário. Modelo de linguagem local pequeno só poderá competir futuramente pela tradução de texto; nunca produz notas nem escreve no Live.

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

`reference` só usa pares sustentados por família/style ou corrupção controlada; não cria pares aleatórios e chama isso de aprendizagem. `humanize` só é promovido se offsets e velocities do corpus mostrarem variedade não artificial. O Groove MIDI Dataset pode ser usado como benchmark/auxiliar separado, sob CC BY 4.0, para medir expressão humana; ele não é misturado silenciosamente ao corpus autoral.

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
| medium | 8–10 camadas, `d_model=512` | somente se curva de escala justificar |

O alvo antigo de 20–50M parâmetros descreve no máximo a faixa medium, não o ponto de partida. Contagem real é calculada e registrada. Modelo maior não avança se small já saturar dados ou qualidade.

### 12.2 Event-based AR

Decoder-only pequeno com embeddings fatorados de tempo, lane, velocity e offset; causal mask e grammar mask. Usa orçamento de parâmetros e passos comparável ao masked small. Avalia especialmente rolls, flams, continuidade e validade.

### 12.3 GrooVAE

Implementação reproduzível e moderna da tarefa de duas barras, sem copiar o stack legado para runtime. Config, conversão e métricas seguem a publicação original onde aplicável. Pesos publicados servem somente como referência; o comparativo principal treina no mesmo split permitido.

## 13. Ambiente e reprodutibilidade

### 13.1 Separação

- preparação/inventário: Windows ou Linux, usando contratos existentes;
- treinamento: ambiente Linux reproduzível;
- produto: Windows x64, helper nativo e ONNX Runtime sem Python;
- dados/checkpoints: workspace externo ao Git;
- manifests/fixtures/relatórios sanitizados: repositório.

### 13.2 GPU local

A RTX 5070 com aproximadamente 12 GB de VRAM, 64 GB de RAM e i9-12900KS é suficiente para smoke, small, ablations e provavelmente o treino completo do modelo especializado com mixed precision, gradient accumulation e activation checkpointing.

O documento anterior fixava PyTorch 2.7/CUDA 12.8. A linha oficial atual mudou: PyTorch 2.12 recomenda CUDA 13.0+ para Blackwell. A implementação não copia números deste texto cegamente; executa um environment probe, registra driver/GPU/compute capability, instala versões pinadas em lock e congela a matriz que passar smoke + checkpoint resume + determinismo declarado.

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

## 15. Avaliação

### 15.1 Integridade

- parse e serialize válidos;
- 100% das saídas aceitas dentro de pitch/lane/time/length limits;
- zero violação de lanes/regiões bloqueadas;
- zero família/near-duplicate conhecida cruzando splits;
- nenhuma consulta do retriever ao blind test;
- zero evento silenciosamente perdido pela representação.

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

### 15.5 Teste humano

Protocolo pré-registrado:

- pelo menos 30 tarefas representativas;
- prompts/controles congelados;
- candidatos anonimizados e volume/kit normalizados;
- comparação neural contra melhor retrieval/transform determinístico;
- avaliação de groove, utilidade, controle, novidade e vontade de usar;
- ordem aleatória e identidade do sistema oculta;
- intervalo de confiança publicado.

Promoção exige que o limite inferior do intervalo para preferência pelo challenger seja maior que 50%, além dos gates automáticos. Se não ocorrer, deterministic/retrieval permanece produto principal.

## 16. Runtime e `.ablx`

### 16.1 Export

PyTorch exporta um grafo ONNX com inputs/outputs e dynamic axes mínimos. Uma suíte dourada compara logits, decoding e groove canônico entre PyTorch e ONNX. Diferença além da tolerância bloqueia o artefato.

### 16.2 Provider

O helper recebe somente `ConditionCard`, referência canônica limitada, seed e limites. Ele não recebe caminho de corpus, comando, shell, token externo ou objeto do Live. Saída passa pelo parser, verifier, anti-copy e mapping antes de aparecer como candidato.

### 16.3 Execution providers

CPU é baseline universal. ONNX Runtime permite providers ordenados com fallback; aceleração GPU é opcional e só entra se estiver empacotada/compatível com single-install. CUDA no computador de desenvolvimento não vira requisito do usuário. DirectML está em manutenção sustentada e WinML é a direção atual da Microsoft; nenhuma delas é selecionada sem spike de embalagem e equivalência.

### 16.4 Orçamento preliminar

- hard cap atual do provider: P95 `<=5 s`, memória `<=512 MiB`, `<=2.048` eventos;
- alvo de produto: candidato warm aproximadamente `<=1 s` no hardware do autor;
- cold start, tamanho do modelo e tamanho total da `.ablx` são medidos antes da promoção;
- nenhuma meta é relaxada depois de ver o blind test.

## 17. Gates binários

| Gate | Passa quando | Falha significa |
|---|---|---|
| G0 Ambiente | GPU/precision/save-resume/dataloader/export smoke passam | parar e corrigir matriz |
| G1 Direitos/origem | 100% dos itens têm registro autoral permitido e digest | item fica fora |
| G2 Dataset | builds repetem; round-trip passa; nenhum cluster cruza split | não treinar |
| G3 Representação | perda/collision/roll coverage publicada e aceita | revisar grid/IR |
| G4 Tiny | overfit e tiny runs aprendem sem colapso/invalidade | corrigir pipeline/modelo |
| G5 Bake-off | candidato vence baselines em validation/humano preliminar | não escalar |
| G6 Full | blind test + originalidade + controles + validade passam | deterministic permanece |
| G7 ONNX | equivalência e orçamento CPU passam | não integrar modelo |
| G8 Produto | candidatos/locks/reference/falhas/readback passam no Live | não promover `.ablx` |

Cada gate produz `stop`, `repeat`, `go limited` ou `go`. Nenhum gate autoriza automaticamente o seguinte; o proprietário aprova a próxima despesa.

## 18. Decomposição futura de implementação

Esta especificação é grande demais para um único plano executável. Depois da revisão do usuário, serão escritos planos separados, nesta ordem:

1. **Training workspace e environment probe** — projeto PyTorch isolado, locks, diagnósticos, smoke e checkpoint resume.
2. **Dataset foundation V3** — schema de treino, canonical store, near-dedupe, cluster/split registry, shards e evidence packet.
3. **Baselines e avaliação** — retrieval/deterministic benchmark, GrooVAE, event AR, métricas e protocolo humano.
4. **Masked HVO Transformer** — tasks, losses, decoding, tiny/1%/10% bake-off.
5. **Full training e model card** — build 100%, run vencedor, blind test, anti-copy e decisão.
6. **ONNX provider** — export, equivalência, quantização, helper e orçamento.
7. **Groove Brain product loop** — dashboard, prompt parser, candidates, locks, reference, mapping e Live readback.

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

## 20. Decisões finais

- Groove Brain é bateria/ritmo, não Music Brain geral.
- O corpus é tratado como autoral conforme declaração explícita do proprietário.
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

## 22. Critério de aprovação desta especificação

O documento está pronto para virar planos de implementação quando o usuário confirmar:

1. o escopo exclusivo de bateria/ritmo;
2. o tratamento do corpus como autoral;
3. a comparação A/B/C em vez de treinar um modelo grande diretamente;
4. o dataset/split/anti-copy antes do full run;
5. a promoção somente após avaliação cega;
6. a separação laboratório PyTorch versus produto ONNX `.ablx`;
7. a decomposição em sete planos independentes.
