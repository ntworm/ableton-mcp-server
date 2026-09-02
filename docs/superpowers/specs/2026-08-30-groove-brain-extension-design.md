# Groove Brain Extension — especificação consolidada de produto e arquitetura

- **Status:** arquitetura de produto preservada; dados e treinamento são regidos pela especificação canônica [Groove Brain — dataset e treinamento neural](2026-08-31-groove-brain-dataset-training-design.md); nenhuma implementação ou treinamento é autorizado por este documento
- **Data:** 2026-08-30
- **Nome de trabalho:** Groove Brain
- **Produto-alvo:** extensão local para Ableton Live, instalada por um único arquivo `.ablx`
- **Escopo musical:** bateria e ritmo; melodia, harmonia, baixo e arranjo harmônico ficam fora

## 1. Decisão em uma frase

Groove Brain será um gerador e navegador inteligente de bateria, totalmente local, aberto como uma interface web modal por uma ação contextual do Ableton Live, capaz de usar a track, o clipe ou a seleção que iniciou a ação como referência, encontrar padrões parecidos, gerar variações ou grooves novos e inserir o resultado diretamente no alvo capturado; para o usuário, toda a instalação obrigatória será um único pacote `.ablx`.

## 2. Resumo executivo

O produto não será um chatbot musical, um serviço de nuvem nem um LLM genérico. O núcleo será um sistema especializado em ritmo com três motores locais:

1. **Catálogo e busca:** organiza MIDIs com proveniência e autorização registradas; o corpus local foi declarado pelo proprietário como material autoral e já possui seed portátil, enquanto caminhos e nomes privados não entram no produto.
2. **Modelo neural de groove:** aprende hits, velocidades e microtiming para gerar, variar, completar e humanizar bateria.
3. **Ponte Ableton:** recebe o contexto da ação contextual, resolve o mapeamento do instrumento e escreve MIDI com segurança no alvo capturado.

A interface principal será um dashboard web local de longa duração **durante uma invocação contextual**. A versão atual do SDK não documenta painel global persistente, acompanhamento da seleção ou serviço de background: fechar o modal encerra a invocação e sua ponte. O texto livre, como “techno sombrio, 128 BPM”, poderá existir como atalho secundário, mas a experiência principal usará controles musicais explícitos, alvo capturado, instrumento, clipe de referência, estilo, densidade, complexidade, swing, novidade e lanes protegidas.

O sistema deve funcionar sem internet depois da instalação. Nenhum MIDI, prompt, telemetria, sessão do Ableton ou inferência sai da máquina. O modelo treinado, o catálogo compacto, o índice de busca, os perfis de mapeamento, a interface e o runtime de inferência serão empacotados como recursos da extensão. Gate 0 já provou instalação, helper e write/readback no Live do autor; máquina limpa, crash, update, uninstall e observação de egress continuam gates antes de promoção.

## 3. Vocabulário e classificação de certeza

Este documento usa três rótulos para não misturar evidência com desejo:

- **Verificado:** observado no repositório, na biblioteca local, na documentação oficial ou em protótipo publicado.
- **Decisão:** comportamento escolhido para o produto.
- **Gate:** hipótese importante que precisa ser provada por um spike antes de continuar.

Termos:

- **Groove:** padrão rítmico MIDI com hits, velocidades e desvios de tempo.
- **Lane:** família de peça, como kick, snare, closed hat ou tom.
- **HVO:** representação separada de hit, velocity e offset.
- **Referência:** clipe MIDI que iniciou a ação contextual e é usado como consulta ou condição.
- **Candidato:** uma possibilidade gerada, ainda não aplicada definitivamente no Live.
- **Perfil de instrumento:** tradução entre lanes canônicas e notas/articulações reais de um Drum Rack ou plugin.

## 4. Tese de produto

### 4.1 Problema

O produtor tem muitos grooves, mas navegar manualmente por milhares de arquivos é lento. Geradores atuais frequentemente ficam fora do fluxo do Ableton, dependem de serviços externos, produzem padrões genéricos ou exigem arrastar arquivos entre aplicações. Também existe uma lacuna entre “gerar notas” e tocar corretamente o Drum Rack ou o Superior Drummer configurado na sessão.

### 4.2 Proposta

Groove Brain deve reduzir o caminho entre intenção e groove útil:

1. abrir o painel dentro do contexto do Live;
2. escolher track, instrumento e destino;
3. escolher um estilo ou selecionar um clipe de referência;
4. gerar ou buscar;
5. ouvir, comparar e ajustar;
6. inserir MIDI correto na track, sem perder o original.

### 4.3 Diferencial realista

O diferencial não é “uma IA que compõe tudo”. É a combinação de:

- corpus especializado em bateria com direitos de ML e distribuição comprovados por item;
- funcionamento integralmente local;
- busca por similaridade e geração no mesmo painel;
- compreensão do contexto do Ableton;
- mapeamento explícito de instrumentos;
- edição por lane, variação, fill e humanização;
- escrita direta e segura no Live;
- instalação única por `.ablx`.

## 5. Objetivos e não objetivos

### 5.1 Objetivos

- Gerar grooves de bateria úteis em produção real.
- Encontrar padrões semelhantes ao clipe contextual.
- Criar variações reconhecíveis sem simplesmente copiar a referência.
- Gerar fills e regenerar somente lanes escolhidas.
- Ajustar densidade, complexidade, swing, humanização e distância da referência.
- Preservar velocity e microtiming, não apenas notas quantizadas.
- Escrever no Drum Rack e no Superior Drummer 3 usando notas corretas.
- Abrir e operar como parte do fluxo do Ableton Live.
- Funcionar offline em runtime.
- Exigir somente a instalação do `.ablx`.

### 5.2 Não objetivos da primeira versão

- Gerar melodia, harmonia, baixo, letra ou estrutura completa da música.
- Conversar como assistente geral.
- Hospedar inferência, biblioteca ou conta na nuvem.
- Suportar todo plugin de bateria existente no primeiro lançamento.
- Alterar automaticamente projetos sem ação explícita do usuário.
- Treinar o modelo dentro do Ableton.
- Publicar ou comercializar durante a fase atual de protótipo.
- Prometer compatibilidade antes de provar o runtime beta de Extensions.

## 6. Público e ambiente inicial

O primeiro usuário é o próprio autor do corpus, em Windows, Ableton Live 12 Suite e hardware local forte. O produto deve, porém, nascer com limites que permitam futura distribuição.

**Decisão:** a primeira plataforma validada será Windows x64. macOS universal será uma fase posterior, porque exige outro binário, assinatura, testes de permissões e empacotamento próprios.

**Verificado:** em 2026-08-30, o SDK público de Ableton Extensions continua identificado como beta e requer versões compatíveis de Live 12 Suite. Isso torna compatibilidade de host um gate explícito, não um detalhe de acabamento.

## 7. Experiência do usuário

### 7.1 Instalação e abertura

1. O usuário instala `GrooveBrain.ablx` pelo fluxo normal de Extensions.
2. A extensão registra **Open Groove Brain** nos escopos contextuais compatíveis, como MIDI clip, MIDI track, clip slot e Arrangement selection.
3. O usuário clica com o botão direito no alvo. A invocação recebe o objeto/selection que iniciou a ação e o congela como contexto inicial.
4. A extensão inicia o helper empacotado, aguarda o health check e abre o dashboard por `showModalDialog` em uma URL loopback autenticada.
5. Nenhuma instalação separada de Python, Node, MCP Server, Remote Script, CUDA ou modelo é exigida.
6. Enquanto o modal está aberto, o usuário pode buscar, gerar e comparar várias alternativas para aquele contexto. Ao fechar, a invocação e o helper terminam; preferências e favoritos podem persistir no storage da extensão.

**Decisão:** se o runtime local não puder iniciar, a UI mostra diagnóstico acionável; não deve instruir o usuário a montar manualmente um ambiente de desenvolvimento.

**Limite confirmado:** a V1 não promete painel dockado, daemon permanente, observação global da seleção ou atualização automática quando o usuário clica em outro item do Set. Um navegador externo persistente só entra se um gate futuro provar uma ponte suportada após o término da ação contextual.

### 7.2 Estrutura do dashboard

O dashboard terá cinco áreas principais:

1. **Ableton Context**
   - tipo e identidade efêmera do objeto que abriu a ação;
   - BPM, compasso e loop quando expostos naquele contexto;
   - track/slot/range capturado e destino resolvido;
   - clipe de referência capturado, quando a ação nasceu de um clipe;
   - devices alcançáveis pelo objeto contextual;
   - perfil de mapeamento ativo.

2. **Source**
   - Browse Library;
   - Selected Clip;
   - Generate New;
   - Variation;
   - Fill;
   - Humanize;
   - Regenerate Lanes.

3. **Musical Controls**
   - gênero e subgênero;
   - BPM e compasso;
   - comprimento em barras;
   - função: main groove, intro, fill, break, ending;
   - densidade;
   - complexidade;
   - swing;
   - humanização;
   - intensidade/velocity;
   - similaridade ↔ novidade;
   - quantidade de candidatos;
   - seed para repetibilidade.

4. **Lane Controls**
   - kick, snare, clap, hats, ride, crash, toms e percussion;
   - solo/mute de visualização;
   - lock para preservar uma lane;
   - regenerate para substituir somente uma lane;
   - densidade e intensidade por lane;
   - alerta de lane sem mapeamento no instrumento atual.

5. **Candidates and Output**
   - visualização em piano roll/step grid;
   - comparação A/B;
   - métricas simples de similaridade, densidade e atividade por lane;
   - Send to Live;
   - Generate & Insert;
   - Replace Explicitly;
   - salvar como favorito local;
   - materializar todos em destinos separados quando possível.

### 7.3 Texto livre

O campo de texto é opcional. “Techno sombrio 128 BPM, duas barras, hats tensos” será convertido localmente em filtros e controles conhecidos. Na primeira versão, isso pode ser um parser determinístico com dicionário multilíngue e sinônimos, não precisa de LLM.

Se futuramente houver um pequeno modelo de linguagem local, ele será apenas um tradutor de intenção para parâmetros. O gerador rítmico continua sendo um modelo especializado e determinístico quanto às suas entradas.

### 7.4 Fluxo A — gerar e inserir rapidamente

1. O usuário abre **Groove Brain** pelo menu contextual de uma MIDI track, clip slot vazio ou seleção de Arrangement compatível.
2. Groove Brain captura o alvo e tenta resolver o instrumento.
3. O usuário escolhe estilo e controles.
4. **Generate & Insert** gera um candidato e cria um novo clipe no destino válido.
5. O clipe aparece imediatamente no Live para edição normal.

Esse é o fluxo de menor atrito.

### 7.5 Fluxo B — comparar candidatos

1. O usuário escolhe **Generate Candidates**.
2. O serviço gera de 4 a 8 candidatos em memória local.
3. O painel permite comparar os padrões sem modificar o projeto.
4. Somente **Send to Live** materializa o candidato escolhido.
5. **Materialize All** cria clipes separados apenas quando o destino e a API permitirem uma operação não destrutiva clara.

### 7.6 Fluxo C — usar um clipe como referência

1. O usuário abre **Groove Brain** pelo menu contextual de um clipe MIDI.
2. O painel mostra esse clipe congelado em **Reference Clip**.
3. O usuário escolhe:
   - Find Similar;
   - Generate Variation;
   - Add Fill;
   - Humanize;
   - Regenerate Selected Lanes.
4. O clipe original é somente leitura por padrão.
5. A saída é criada como novo clipe, a menos que o usuário escolha explicitamente substituir.

### 7.7 Fluxo D — navegar pela biblioteca

1. O usuário filtra gênero, subgênero, BPM, compasso, feel e função.
2. O índice retorna resultados próximos e diversos.
3. O usuário pode aumentar ou reduzir a diversidade dos resultados.
4. O padrão escolhido é remapeado para o instrumento do contexto capturado e enviado ao alvo revalidado.

## 8. Semântica de candidatos e escrita no Live

### 8.1 Tipos de destino

A ponte representa o destino com uma abstração comum:

- `SessionSlotTarget`: track e slot de Session View;
- `ArrangementRangeTarget`: track, posição e duração em Arrangement View;
- `ExistingClipTarget`: clipe já existente para leitura ou substituição explícita.

**Decisão:** `SessionSlotTarget` é o primeiro caminho de escrita. `ArrangementRangeTarget` permanece desabilitado até provar precondições de overlap, escrita parcial, undo agrupado e readback na matriz exata de compatibilidade. `ExistingClipTarget` é leitura por padrão e só aceita substituição por comando explícito.

### 8.2 Regras de segurança

- Geração não altera o Live enquanto calcula.
- **Send to Live** cria um clipe novo ou usa um slot vazio por padrão.
- Variação, fill e humanização preservam o original por padrão.
- Substituição requer ação separada e confirmação clara.
- O alvo é capturado antes da geração e revalidado imediatamente antes da escrita.
- Se track, clipe, dispositivo, compasso ou mapeamento mudarem, a escrita é interrompida.
- Depois da escrita, a extensão lê o clipe de volta e compara quantidade, pitch, tempo, duração e velocity.
- Uma resposta ambígua não é repetida automaticamente, evitando duplicação.
- Candidatos inválidos, notas fora do perfil ou tempos fora do clipe nunca são enviados.

Não se presume rollback transacional. Até prova contrária, “undo agrupado” significa somente uma entrada coerente no histórico do Live; não garante reversão automática se o host falhar entre criar o clipe e definir suas notas.

### 8.3 Matriz mínima de precondições

| Alvo observado | Operação padrão | Resultado permitido |
|---|---|---|
| Session slot vazio e ainda vazio | create + set notes + readback | novo clipe e receipt verificado |
| Session slot ocupado | nenhuma escrita | pedir outro slot ou substituição explícita |
| Clip existente usado como referência | leitura | criar saída em outro alvo |
| Clip existente com Replace Explicitly | snapshot + set notes + readback | substituição confirmada; sem retry ambíguo |
| Arrangement sem overlap | bloqueado até gate específico | criar somente após testes de falha e undo |
| Arrangement com overlap parcial/total | nenhuma escrita na V1 | exigir novo range |
| Handle, track, device ou mapping mudou | nenhuma escrita | invalidar candidato para aquele alvo |

Toda tentativa devolve um receipt local com tipo do alvo, handle efêmero, precondições observadas, hash do payload, resultado de create/set, readback e estado final conhecido. Testes devem injetar falha entre `create` e `set notes`, durante readback e no encerramento do host.

### 8.4 Preview

O primeiro preview garantido é visual e local no painel. Preview de áudio pelo instrumento real pode usar um clipe temporário somente quando o SDK provar criação e limpeza atômicas. Não será criada uma mutação oculta só para fingir preview.

## 9. Arquitetura de runtime

```text
┌──────────────────────── Ableton Live ────────────────────────┐
│ Extension Host                                               │
│  - lê o objeto/selection da ação via Extensions SDK           │
│  - resolve alvo e aplica MIDI                                │
│  - inicia/encerra helper local                               │
│  - abre dashboard local                                      │
└───────────────┬──────────────────────────▲────────────────────┘
                │ loopback autenticado     │ comandos/estado
                ▼                          │
┌──────────────────── Groove Brain Helper ─────────────────────┐
│ API local + lifecycle                                        │
│  ├─ catálogo/metadados + busca por similaridade              │
│  ├─ runtime de inferência                                    │
│  ├─ validação musical e anti-cópia                           │
│  ├─ perfis de instrumentos                                   │
│  └─ servidor de assets web                                   │
└───────────────┬──────────────────────────▲────────────────────┘
                │                          │
                ▼                          │
┌──────────────────────── Web UI local ────────────────────────┐
│ dashboard, grid, controles, candidatos e diagnósticos        │
└───────────────────────────────────────────────────────────────┘
```

### 9.1 Responsabilidades

**Extension Host**

- única camada que fala diretamente com a API do Live;
- mantém somente as referências efêmeras daquela invocação e revalida alvos;
- não carrega o modelo pesado dentro do processo do host;
- supervisiona o helper;
- traduz estado e operações para um protocolo interno versionado.

**Helper local**

- processo filho pertencente à extensão;
- serve UI, busca, modelo e perfis;
- não acessa o Live diretamente;
- não abre portas de rede pública;
- pode ser reiniciado de forma limitada dentro da mesma invocação;
- registra logs locais sanitizados e limitados.

**Web UI**

- é cliente do helper e da ponte;
- não recebe acesso arbitrário ao filesystem;
- não executa inferência remota;
- continua útil mesmo sem campo de prompt.

### 9.2 Por que o modelo fica fora do host

Inferência nativa, memória e crashes não devem comprometer o processo de Extensions ou o Live. Um helper isolado permite controlar versão, threads, CPU/GPU, watchdog e recuperação. Também evita exigir que o host carregue bindings nativos não suportados.

## 10. O pacote `.ablx`

### 10.1 Conteúdo conceitual

```text
GrooveBrain.ablx
├─ manifest.json
├─ dist/
│  └─ extension.js
├─ ui/
│  ├─ index.html
│  └─ assets/*
├─ runtime/
│  └─ windows-x64/
│     └─ groove-brain-helper.exe
├─ models/
│  ├─ groove-brain.onnx
│  └─ model-card.json
├─ data/
│  ├─ taxonomy.json
│  ├─ curated-catalog.sqlite
│  ├─ similarity-index.bin
│  └─ mappings/*
└─ licenses/*
```

O formato final pode ser compactado ou reorganizado pela CLI, mas esses recursos fazem parte do mesmo artefato instalado. O catálogo bundled será uma curadoria/codificação compacta definida pelo orçamento da Fase 1; a visão do produto não exige empacotar todos os arquivos MIDI brutos.

### 10.2 O que já está verificado

- O projeto atual compila uma Extension com `manifest.json` e `dist/extension.js`.
- A CLI instalada expõe inclusão de arquivos extras no empacotamento.
- O SDK expõe diretórios de storage e temporários.
- O SDK expõe leitura e escrita de notas MIDI e abertura de UI por URL local.
- O protótipo atual consegue manter um servidor loopback durante sua ativação, mas isso não prova que o lifecycle seja suportado como painel global persistente.

### 10.3 O que ainda precisa ser provado

Antes de treinar um modelo de produção, um spike mínimo precisa passar por esta matriz binária:

| Prova | Critério de aprovação |
|---|---|
| Matriz fixada | registrar build exata do Live, hash/versão do SDK e CLI, Node do host, Windows e arquitetura |
| Inventário do pacote | listar e hashear conteúdo real do `.ablx`, incluindo UI e binário dummy |
| Máquina limpa | instalar sem repositório, Python, Node de desenvolvimento, MCP ou Remote Script |
| Descoberta de recursos | localizar assets sem depender de CWD ou caminho do repositório |
| Spawn | executar helper incluído sem cópia/instalação manual e verificar hash antes de executar |
| Health/UI/Live | abrir modal local, trocar mensagem autenticada e ler/escrever/readback de um clipe de teste |
| Lifecycle normal | fechar modal e comprovar encerramento do helper/árvore sem resíduos indevidos |
| Falhas | matar helper, Live e host separadamente; nenhum processo fica órfão e o Set não recebe retry ambíguo |
| Concorrência | duas invocações/instâncias não compartilham porta, token, storage efêmero ou alvo |
| Upgrade/uninstall | atualizar e remover sem perder perfis do usuário nem deixar runtime executável abandonado |
| Offline/egress | executar com rede bloqueada e comprovar zero tentativa de egress |
| Segurança Windows | documentar SmartScreen, assinatura, permissões e resultado do antivírus suportado |

**Gate 0 — Single-install proof:** o produto fica bloqueado até que essa matriz passe numa máquina sem ambiente de desenvolvimento. Se o helper nativo incluído falhar, a única alternativa admissível é outro runtime também contido no `.ablx` e novamente submetido à matriz; instalar componentes separados não é fallback autorizado.

### 10.4 Lifecycle

1. Uma ação contextual captura seu objeto/selection e cria um namespace efêmero.
2. A Extension cria credencial de sessão e canal pai privado; nenhum segredo entra em argv.
3. O helper verifica o próprio recurso, faz bind atômico em `127.0.0.1:0` e devolve endpoint pelo canal pai, evitando corrida de “escolher porta e depois abrir”.
4. A Extension aguarda health check autenticado com timeout curto e abre o modal.
5. Toda requisição HTTP/WebSocket valida token, Host, Origin e namespace da instância.
6. Heartbeat, parent-death watchdog, Job Object/equivalente e limite de reinícios impedem helper órfão e retry storm.
7. Ao fechar modal, terminar a ação, desativar Extension ou sair do Live, o pai solicita shutdown, encerra a árvore se necessário e verifica a saída.

O helper é idempotente por invocação. Não existe daemon global permanente. Estado efêmero é isolado por instância; somente preferências, mappings e favoritos explicitamente persistentes compartilham storage com locking e schema versionado.

### 10.5 Tamanho e desempenho-alvo

Metas iniciais, sujeitas a medição em P50/P95, cold/warm, CPU-only e com o Live sob carga:

- pacote core preferencialmente abaixo de 500 MiB;
- painel útil em até 5 segundos em máquina-alvo;
- busca em até 200 ms para consultas comuns;
- 8 candidatos em até 2 segundos com aceleração ou 5 segundos em CPU suportada;
- RAM de runtime preferencialmente abaixo de 2 GiB;
- fallback CPU sempre disponível no pacote Windows.

Ao fim da Fase 1, um orçamento obrigatório mede 1%, 10% e 100% do catálogo e registra bytes comprimidos/instalados para: padrões, metadados, embeddings, ANN, modelo, runtime, UI e licenças. Como referência, 172.133 embeddings float32 de 256 dimensões já ocupam cerca de 168 MiB antes do índice e dos outros recursos; quantização ou curadoria precisam ser decisões medidas.

Packs opcionais de estilo podem existir futuramente, mas não são usados para esconder dependências obrigatórias da primeira versão.

## 11. Ponte de contexto com o Ableton

### 11.1 Snapshot exposto ao dashboard

O estado mínimo versionado inclui somente o que a ação e seus objetos alcançáveis realmente expõem:

- scope da ação e handle/selection efêmero;
- track, clip, slot ou range contextual;
- notas completas do clipe de referência, quando houver;
- tempo, compasso, loop e devices quando alcançáveis;
- Drum Rack, chains e `receivingNote` quando expostos;
- nome/classe do plugin quando disponível;
- perfil de instrumento ativo;
- capabilities comprovadas naquela matriz de host.

A V1 não presume identidade estável do Set, lista global de seleção nem eventos de mudança de seleção. O painel recebe um snapshot congelado e respostas de revalidação. IDs internos do Live nunca são persistidos entre invocações.

### 11.2 Comandos internos

O protocolo precisa de operações pequenas e tipadas:

- `get_invocation_context`
- `get_reference_clip`
- `select_target`
- `resolve_instrument`
- `create_midi_clip`
- `replace_midi_clip_explicitly`
- `readback_clip`
- `save_mapping_profile`

O helper devolve MIDI canônico. A Extension faz o remapeamento final e a escrita, porque só ela conhece o estado atual do Live.

## 12. Mapeamento de instrumentos

### 12.1 Ontologia canônica

O modelo não aprende cada número MIDI de cada plugin como uma classe independente. Ele usa lanes semânticas canônicas, inicialmente:

- kick;
- snare center;
- snare rim/side;
- clap;
- closed hat;
- open hat;
- pedal hat;
- ride;
- crash;
- tom high;
- tom mid;
- tom low;
- percussion 1–4.

Articulações adicionais podem ser preservadas no corpus e agrupadas de forma hierárquica, sem inflar o primeiro modelo.

### 12.2 Ableton Drum Rack

**Parcialmente verificado:** o SDK vendorizado expõe Drum Rack, chains e `receivingNote`, mas não documenta pad names ou chain names como fonte semântica completa. `Device.name` e parâmetros podem ajudar na detecção, sem provar qual peça cada nota representa.

Resolução:

1. ler `receivingNote`, estrutura de chains e metadados de device realmente disponíveis;
2. classificar por regras e sinônimos;
3. mostrar confiança por lane;
4. exigir perfil/manual mapping quando a assinatura não for inequívoca;
5. salvar o perfil local por assinatura estrutural do rack.

O usuário sempre pode clicar num pad e escolher sua lane semântica.

### 12.3 Superior Drummer 3

O Live normalmente enxerga o plugin e eventos MIDI, mas não deve ser tratado como fonte confiável de todo preset/articulação interno do SD3.

**Decisão:** suporte profundo será baseado em perfis explícitos:

- perfil default conhecido;
- perfis por mapping preset;
- importação de mapa quando houver formato suportado;
- aprendizado de correções manuais;
- detecção por nome/classe do plugin;
- confirmação quando dois perfis forem plausíveis.

Não haverá promessa de “descobrir magicamente todo kit do Superior Drummer”. Se o preset do usuário divergir, o painel mostra o problema e resolve com um editor de mapping rápido.

A V1 só declara suporte aos presets/mapas SD3 que forem nomeados, auditados e incluídos numa matriz `preset × articulação × nota`. Até essa matriz existir, selecionar manualmente um perfil é obrigatório. Detecção por nome pode sugerir um perfil, nunca aplicá-lo silenciosamente quando houver ambiguidade.

### 12.4 Registro de perfis

Cada perfil inclui:

- identificador e versão;
- tipo de instrumento;
- critérios de detecção;
- lane → uma ou mais notas/articulações;
- regra de escolha da articulação: fixa, alternância, round-robin, condição ou manual;
- notas proibidas ou reservadas;
- aliases;
- origem: bundled, imported ou user;
- data de alteração;
- assinatura opcional da estrutura detectada.

Perfis do usuário ficam no diretório de storage e sobrevivem a atualizações sem modificar o pacote instalado.

## 13. Corpus e governança de dados

### 13.1 Fonte

O inventário completo encontrou 183.429 arquivos MIDI, dos quais 180.614 são válidos, 2.815 têm falhas explícitas de parser e 11.296 repetem um digest bruto. O seed V2 promovido contém 1.685 representantes. A hierarquia contém nomes de produtos usados como referência organizacional, mas o proprietário declarou que os padrões foram gerados/exportados por processo próprio, pertencem a ele e estão autorizados para este projeto.

Essa declaração é registrada como `source_kind=author`, `license_id=user-owned` e `redistribution=full`. Ela remove o bloqueio interno anterior baseado na suposição incorreta de que os arquivos eram componentes comprados da Toontrack; não constitui certificação jurídica externa.

### 13.2 Proveniência

Cada fonte precisa de evidência que cubra, no mínimo, origem, processamento para ML, treinamento, retenção de derivados, uso dos pesos e distribuição planejada. Para o corpus atual, a evidência raiz é a declaração autoral do proprietário, ligada por manifest aos hashes dos itens.

Fontes admissíveis: material criado pelo usuário com cadeia autoral clara; material encomendado com cessão/licença explícita para ML; corpus opt-in com contrato compatível; e obras realmente em domínio público ou CC0 após auditoria individual. Fonte sem evidência suficiente falha fechada e permanece em quarentena.

### 13.3 O corpus bruto não entra no Git

- MIDIs brutos permanecem fora do repositório.
- O pipeline cria manifestos reproduzíveis com hashes e metadados.
- Dados temporários, checkpoints e caches usam workspace dedicado.
- O pacote de produto contém somente artefatos derivados necessários: modelo, índice, catálogo canônico e metadados permitidos.
- Caminhos pessoais e nomes desnecessários não aparecem no `.ablx`.

### 13.4 Pipeline de preparação

1. inventariar arquivos sem alterá-los;
2. validar MIDI e extrair tracks/eventos;
3. normalizar tempo musical sem destruir offsets;
4. mapear pitches para ontologia canônica;
5. segmentar em janelas musicais coerentes;
6. inferir BPM, compasso, número de barras, densidade, swing, função e estilo;
7. preservar rótulos confiáveis extraídos da hierarquia de pastas;
8. marcar confiança e origem de cada rótulo;
9. deduplicar por arquivo, conteúdo canônico e similaridade próxima;
10. incorporar lineage disponível do gerador anterior: versão, template, prompt, batch, seed e transformação;
11. agrupar lineage/famílias antes de dividir treino/validação/teste;
12. gerar fingerprints, embeddings e estatísticas somente com o train split quando houver aprendizado;
13. produzir relatórios de qualidade e cobertura.

### 13.5 Labels

**Corrigido em 2026-09-02.** Esta seção afirmava que a hierarquia carrega BPM.
Medido, ela não carrega: o seed promovido tem `genre` em 982 dos seus 1.685
artefatos (58,3%), vindo dos nomes de pasta, e **zero** linhas no eixo de
andamento. O gênero de pasta existe; o BPM de pasta nunca chegou ao índice.

O andamento veio dos bancos `midiDB` das próprias bibliotecas Toontrack, junto
com um segundo gênero. O sidecar extraído deles cobre 109.554 caminhos, todos com
gênero e todos com andamento, em 15 gêneros distintos — `Pop/Rock/Country`
responde por 57.670 arquivos e `Metal` por 21.672. Isso é rótulo do fornecedor,
não inferência: não precisa de classificador nem de validação humana.

Os dois vocabulários de gênero convivem em vez de um substituir o outro. O da
pasta é o mais fino (`rock`, `metal`, `pop`, `fusion`) e cobre só parte do
corpus; o do fornecedor é o mais grosso (`pop_rock_country` junta três gêneros)
e cobre tudo que ele conhece. Trocar um pelo outro perderia precisão de busca,
então o build une os dois no mesmo eixo.

O que continua valendo da formulação original:

- nomes de pasta são weak labels para feel e seção, não verdade absoluta;
- uma taxonomia normalizada liga aliases e hierarquias;
- “dark techno” não pode depender apenas da interseção textual exata;
- um classificador/cluster e inspeção humana validam rótulos escassos;
- o painel mostra apenas categorias com cobertura e qualidade mínimas.

O que deixa de valer: tratar a hierarquia como fonte de BPM. O build lê o
sidecar do fornecedor para isso, e um build sem ele não publica o eixo `bpm` e
mantém apenas o `genre` derivado do caminho.

### 13.6 Divisão sem vazamento

O split nunca é aleatório por arquivo individual. Arquivos iguais, transpostos no pitch de bateria, levemente deslocados ou pertencentes à mesma família devem ficar no mesmo lado do split.

Ordem:

1. dedupe exato;
2. canonicalização por lane;
3. cluster de near-duplicates;
4. cluster por lineage do gerador anterior quando esses metadados existirem;
5. cluster por origem/pacote/família;
6. split de clusters em train/validation/test;
7. treinamento de embedding/ranker somente no train;
8. congelamento do blind test com acesso auditado e retriever impedido de consultar holdouts.

Sem isso, métricas seriam artificialmente altas e o modelo poderia apenas memorizar variações do teste.

**Risco conhecido:** ainda não foi confirmado se prompt/template/batch/versão do gerador anterior foram preservados. Se não existirem, o pipeline usa clustering conservador por conteúdo, origem e assinaturas de geração, e o model card registra que independência por lineage não pôde ser provada. Isso não impede protótipo, mas impede alegações fortes de generalização.

## 14. Representação musical

### 14.1 HVO por lane

Para cada passo e lane:

- `H`: probabilidade/presença do hit;
- `V`: velocity normalizada;
- `O`: offset contínuo em relação à grade.

Metadados condicionais incluem BPM, compasso, estilo, função, feel, número de barras, densidade e perfil de tarefa.

### 14.2 Envelope MIDI lossless

HVO é projeção para aprendizado, não formato mestre. Cada evento original preserva num envelope lossless, quando o SDK/arquivo fornecer:

- pitch e lane/articulação;
- start time e duration;
- velocity e release velocity;
- mute;
- probability e velocity deviation;
- identificador de origem e ordem para colisões.

Lanes bloqueadas transportam os eventos originais completos e são reinseridas depois do decoding; não são reconstruídas por HVO. Notas geradas recebem política explícita de duration e atributos opcionais. Rolls, flams e múltiplos hits na mesma célula usam subeventos/offsets ou representação event-based complementar; nunca são silenciosamente fundidos.

### 14.3 Resolução e duração

A baseline usará duas barras e resolução suficiente para semicolcheias, preservando offset contínuo. Uma configuração de 64 passos por duas barras será testada quando rolls e subdivisões de 32 avos forem relevantes. A escolha final depende da cobertura real do corpus e de ablação, não de preferência estética.

Padrões maiores serão gerados por blocos com contexto ou por modelo hierárquico somente depois que a qualidade de duas barras estiver provada.

### 14.4 Compasso

4/4 será o primeiro caminho otimizado, mas o schema não fixa 4/4. Outros compassos entram somente com cobertura suficiente e teste separado.

## 15. Sistema de busca e referência

### 15.1 Busca híbrida

Cada padrão terá:

- filtros estruturados: estilo, BPM, compasso, barras, função, densidade;
- fingerprint rítmico por lane;
- embedding musical aprendido;
- estatísticas interpretáveis.

A consulta combina filtros rígidos, distância de embedding e diversidade. O índice aproximado retorna vizinhos rapidamente; uma etapa de reranking elimina duplicatas e equilibra familiaridade com variedade.

### 15.2 Find Similar

O clipe do Ableton passa pelo mesmo canonicalizador. O sistema:

1. detecta ou recebe o mapping;
2. converte as notas em HVO canônico;
3. extrai fingerprint e embedding;
4. busca candidatos compatíveis com BPM/compasso;
5. reranqueia por lanes escolhidas e diversidade;
6. remapeia o resultado para o instrumento-alvo.

### 15.3 Retriever antes do gerador

O retriever é um produto útil mesmo sem rede neural generativa e serve como baseline obrigatório. O modelo só será promovido se gerar valor maior que:

- recuperação do vizinho mais próximo;
- escolha aleatória dentro de filtros corretos;
- transformações determinísticas de density/swing/velocity;
- combinação controlada de lanes de grooves recuperados.

## 16. Modelo neural

### 16.1 Tipo de modelo

O primeiro challenger será um Transformer condicional e mascarado, especializado em grooves. Não é um LLM de texto. Ele só vira modelo principal depois de vencer os baselines e pelo menos um decoder alternativo em avaliação cega.

Baseline proposta:

- 6 camadas;
- `d_model = 256`;
- 8 attention heads;
- feed-forward de 1024;
- dropout de 0,1;
- heads separados para hit, velocity e offset;
- embeddings de lane, posição, tarefa e condições;
- treinamento multi-tarefa por máscaras.

Uma variante maior, por exemplo `d_model = 512`, só continua se curvas de qualidade versus custo mostrarem ganho real. O orçamento inicial limita parâmetros, tamanho ONNX, RAM e latência antes de ampliar largura/camadas.

### 16.2 Tarefas de treinamento

O mesmo backbone aprende:

- geração com todos os passos mascarados;
- variação com parte dos eventos preservada;
- infilling de região temporal;
- infilling de lanes;
- fill condicionado por posição/seção;
- humanização de sequência quantizada;
- reconstrução de velocity e microtiming;
- continuação curta com contexto anterior;
- referência com força de similaridade controlável.

Máscaras representam exatamente locks e regiões escolhidas no painel, alinhando treinamento com uso real.

Pares de treino são construídos e versionados por tarefa:

- humanize: entrada quantizada/velocity simplificada → evento expressivo original;
- variation: subconjunto preservado + corrupção controlada → padrão original ou par da mesma família;
- fill: contexto/posição de seção + região final mascarada → fill observado, com superamostragem e negativos;
- lane infill: uma ou mais lanes removidas → groove completo;
- reference: padrão A → padrão B somente quando lineage/style/família sustentarem a relação.

Se os dados não preservarem expressão real, a tarefa de humanize não será apresentada como aprendida; usa baseline separado ou dados humanos licenciados e claramente segregados.

### 16.3 Condições

- estilo/subgênero;
- BPM e compasso;
- função musical;
- densidade global e por lane;
- complexidade;
- swing/feel;
- intensidade;
- força de mutação;
- comprimento;
- lanes bloqueadas;
- embedding opcional da referência.

### 16.4 Funções de perda

- hit: binary cross-entropy ou focal loss conforme desbalanceamento;
- velocity: regressão apenas onde existe hit;
- offset: regressão apenas onde existe hit;
- regularização de densidade/controle quando necessária;
- contrastive loss opcional para embedding de similaridade;
- penalidades musicais somente se métricas provarem benefício.

### 16.5 Decoding e inferência

O challenger masked usa decoding iterativo: inicia nas células mascaradas, prevê probabilidades, amostra hits por temperatura/threshold por lane, fixa primeiro as decisões de maior confiança e repete por um número limitado de passos; velocity/offset são condicionados somente aos hits finais. Seeds diferentes geram candidatos, mas locks e envelope lossless são reinseridos de forma determinística.

Serão comparados pelo menos:

- masked iterative Transformer;
- decoder autoregressivo/event-based pequeno, especialmente para rolls e continuidade;
- GrooVAE/HVO reproduzível;
- retriever + transformações determinísticas.

A escolha final mede qualidade, controle, diversidade, tamanho, CPU e estabilidade de exportação; não é decidida pela training loss.

1. o painel envia controles e referência canônica;
2. o retriever fornece exemplos/âncoras quando o modo pede;
3. o modelo amostra candidatos com seeds distintas;
4. pós-processamento valida colisões, limites e densidade;
5. detector anti-cópia aplica distância e invariâncias calibradas por tarefa; lanes bloqueadas e referência são excluídas da parte atribuída ao modelo;
6. candidatos válidos voltam ao painel;
7. a Extension remapeia e aplica o escolhido.

### 16.6 Exportação

O modelo aprovado será exportado para um runtime estável e empacotável, preferencialmente ONNX. O helper oferece CPU como baseline universal e aceleração local somente quando detectada. Treinamento usa PyTorch; o usuário final não recebe ambiente Python.

### 16.7 Hardware de desenvolvimento

O ambiente informado — RTX 5070 com aproximadamente 12 GB, 64 GB de RAM e i9-12900KS — é suficiente para baselines e modelos médios especializados com mixed precision, gradient accumulation e checkpoints controlados. Não justifica começar por um modelo gigantesco.

O espaço livre observado anteriormente, próximo de 199 GB, exige orçamento: corpus processado, embeddings, checkpoints e caches precisam de política de retenção antes do treino completo.

## 17. Qualidade, originalidade e anti-memorização

O corpus foi produzido por um processo algorítmico/LLM anterior. Isso aumenta escala, mas pode carregar padrões repetitivos, artefatos e famílias muito próximas. Volume sozinho não prova qualidade.

Controles obrigatórios:

- dedupe exato e canônico;
- cluster de near-duplicates;
- score de validade e diversidade;
- auditoria de distribuição por lane/style/BPM;
- blind test separado por família;
- nearest-neighbor de toda saída avaliada;
- limiar de rejeição de cópia para geração;
- avaliação humana sem mostrar a origem;
- comparação com retriever e transforms determinísticos;
- modelo card com dados, limites e métricas.

Uma saída recuperada da biblioteca é marcada como **Library Result**. Uma saída neural é marcada como **Generated**. O produto não mistura as duas origens silenciosamente.

O detector anti-cópia terá limiares separados para geração livre, variação, fill e lane infill. A calibração usa pares exatos, near-duplicates conhecidos e exemplos musicais distintos; registra se a distância ignora velocity, offsets, transposição de mapping, repetição de barra e lanes bloqueadas. Holdouts nunca participam do índice consultável durante avaliação.

## 18. Segurança, privacidade e offline

### 18.1 Política de rede

- bind exclusivo em `127.0.0.1`/loopback;
- porta aleatória, não fixa;
- token de alta entropia por invocação, transferido fora de argv/logs;
- validação de `Host` e `Origin`;
- CORS fechado;
- CSP restritiva na UI;
- nenhuma chamada de internet no runtime normal;
- nenhuma telemetria por padrão;
- nenhum CDN, fonte remota ou asset externo.

### 18.2 Fronteiras

- O helper não recebe comandos arbitrários de shell.
- A UI não escolhe caminhos arbitrários do filesystem.
- A Extension valida todo payload antes de chamar o SDK.
- O modelo não pode produzir pitches fora do perfil permitido.
- Catálogo, modelo e perfis bundled são versionados e verificados.
- Logs não contêm notas completas, caminhos pessoais, tokens ou nomes desnecessários de projeto.

### 18.3 Reprodutibilidade

Cada geração registra localmente, se o usuário habilitar histórico:

- versão do modelo;
- hash do modelo, runtime, execution provider e pós-processamento;
- parâmetros;
- seed;
- hash da referência, não o arquivo bruto;
- perfil de instrumento;
- hash do resultado.

Seed só garante repetição dentro da mesma combinação de modelo, runtime, execution provider e pós-processamento. Para recall exato após updates ou troca de hardware, o histórico salva o resultado canônico completo; não promete determinismo bit-a-bit universal.

## 19. Erros e recuperação

| Situação | Comportamento |
|---|---|
| Helper não inicia | diagnóstico local, caminho de logs e botão de tentar novamente |
| Modelo incompatível/corrompido | bloqueia inferência; biblioteca e diagnóstico podem continuar |
| Objeto contextual deixa de resolver | invalida o alvo e pede nova invocação pelo menu contextual |
| Track/clipe mudou durante geração | não escreve; mostra diff relevante |
| Instrumento desconhecido | abre editor de mapping; não adivinha silenciosamente |
| Lane sem nota | candidato continua visível, mas envio é bloqueado ou lane é explicitamente omitida |
| Slot ocupado | oferece novo slot/destino; nunca sobrescreve por acidente |
| Escrita ambígua | lê de volta; não repete automaticamente |
| Sem GPU | usa CPU e mostra estimativa de tempo |
| Índice indisponível | geração pode continuar se independente; busca fica desabilitada |
| UI fechada | invocação/helper terminam; próxima ação restaura somente preferências, mappings, favoritos e resultados salvos |

## 20. Avaliação e critérios de promoção

### 20.1 Dados

- porcentagem de MIDI válido;
- cobertura de mapping;
- duplicação exata e próxima;
- distribuição por estilo, BPM, compasso, função e lane;
- taxa de labels de baixa confiança;
- ausência de famílias cruzando splits.

### 20.2 Modelo offline

- precisão/recall/F1 de hits por lane;
- erro de velocity e offset condicionado a hit;
- aderência a densidade, BPM, função e lanes bloqueadas;
- diversidade intra-lote;
- distância da referência conforme slider;
- taxa de colisões e eventos inválidos;
- taxa de rejeição por near-copy;
- comparação cega com baselines.

### 20.3 Produto no Live

- tempo de abertura a frio e quente;
- latência de busca e geração;
- sucesso de mapeamento automático;
- sucesso de create/write/readback;
- zero overwrite não autorizado;
- recuperação após helper crash;
- instalação limpa numa máquina sem toolchain;
- operação comprovada sem acesso à internet.

### 20.4 Métrica humana principal

Em teste cego, um produtor deve responder: “eu manteria e trabalharia a partir deste groove?”. A promoção exige melhora mensurável sobre busca e transformações determinísticas, não apenas loss menor.

## 21. Fases e gates

### Fase 0 — prova da embalagem e da ponte

Entregas:

- `.ablx` mínimo com helper dummy incluído;
- UI local incluída;
- comunicação autenticada;
- leitura de contexto;
- escrita e readback de um clipe de teste;
- lifecycle e uninstall verificados.

**Gate:** 100% da matriz binária do Gate 0 passa e a evidência registra builds/hashes. Sem isso, parar e revisar arquitetura antes de treinar pesado.

### Fase 1 — auditoria e dataset canônico

Entregas:

- manifest imutável;
- relatório de qualidade;
- ontologia e mappings;
- dedupe/near-dedupe;
- taxonomia;
- splits congelados;
- conjunto de avaliação humana.

**Gate preliminar:** ≥99% dos arquivos parseáveis ou todos os descartes explicados; zero duplicata exata atravessando splits; auditoria amostral de near-duplicate aceita; lineage usado quando disponível; blind test congelado; orçamento 1%/10%/100% cabe no disco e no limite proposto do pacote. Limiares finais são fixados antes de rodar o corpus completo, sem ajustá-los depois de ver o test.

### Fase 2 — produto sem modelo generativo

Entregas:

- catálogo;
- busca por filtros;
- Find Similar;
- transformações determinísticas;
- UI e Send to Live;
- Drum Rack e perfil SD3.

**Gate preliminar:** em roteiro congelado com pelo menos 30 tarefas, ≥90% concluem sem workaround de desenvolvimento; 100% das escritas aprovadas têm receipt/readback; zero overwrite não autorizado; busca P95 ≤200 ms no hardware mínimo definido; avaliação cega prefere o resultado filtrado/transformado ao random baseline com limite inferior do intervalo de confiança acima de 50%.

### Fase 3 — baselines neurais

Entregas:

- GrooVAE/HVO baseline reproduzível;
- Transformer mascarado pequeno;
- tarefas generate/variation/fill/lane infill/humanize;
- avaliação comparativa;
- export ONNX.

**Gate preliminar:** teste cego com protocolo e tamanho de amostra pré-registrados prefere o challenger ao melhor baseline com limite inferior de confiança acima de 50%; zero violação de lanes bloqueadas; zero evento estrutural inválido na suíte; aderência de controles melhora o baseline; ONNX respeita orçamento de tamanho, RAM e latência P95 no CPU mínimo. Falhar em qualidade encerra escala do modelo e mantém a Fase 2 como produto útil.

### Fase 4 — integração do gerador

Entregas:

- candidatos;
- locks/regenerate;
- referência contextual;
- anti-cópia;
- histórico/seed;
- performance CPU/GPU;
- falhas e recuperação.

**Gate preliminar:** pelo menos 500 operações end-to-end e testes de falha injetada; zero overwrite não autorizado; 100% dos resultados reportados como sucesso passam no readback; nenhum helper órfão nos testes; generation P95 dentro do orçamento; mapping desconhecido falha fechado. Arrangement continua fora se sua matriz específica não passar.

### Fase 5 — consolidação do protótipo

Entregas:

- testes longos em projetos reais;
- redução de pacote/memória/latência;
- mapeamentos refinados;
- model card e documentação;
- teste offline e máquina limpa;
- decisão explícita sobre macOS e distribuição.

Não há fase de lançamento autorizada neste plano.

### 21.1 Protocolo comum de promoção

Cada gate produz um evidence packet versionado com:

- matriz exata de hardware, Windows, Live, SDK, CLI, Node/runtime e hashes;
- dataset/split/model/index versions;
- comandos, casos, amostra e resultados brutos;
- P50/P95 cold/warm e memória residente;
- falhas, desvios e itens desabilitados;
- decisão `stop`, `repeat`, `go limited` ou `go`;
- responsável e aprovação explícita do product owner.

Todo upgrade de Live/SDK/CLI ou mudança no helper reexecuta Gate 0 e a suíte de escrita. Métricas e thresholds são congelados antes do test set. `Go limited` precisa listar exatamente a capability desabilitada; não transforma hipótese em promessa. Rollback retorna ao último artefato e matriz aprovados.

## 22. Alternativas consideradas

### 22.1 MCP Server/Remote Script como dependência principal — rejeitado

É útil para desenvolvimento e automação geral, mas contradiz a instalação única e adiciona processos/configuração que o usuário final não deveria conhecer. Pode continuar como ferramenta opcional de laboratório, não como requisito do Groove Brain.

### 22.2 LLM de texto como gerador central — rejeitado

É maior, menos previsível e inadequado para representar hits, velocity e microtiming com controles finos. Texto pode traduzir intenção; o gerador deve ser musical e especializado.

### 22.3 Modelo carregado no processo da Extension — rejeitado

Aumenta risco de crash, bloqueio, incompatibilidade nativa e consumo dentro do host. O helper isolado é a fronteira escolhida.

### 22.4 Interface online — rejeitada

Quebra offline, privacidade e previsibilidade. A UI é web por tecnologia, mas servida somente da máquina local.

### 22.5 Treinar primeiro e integrar depois — rejeitado

Pode produzir um bom notebook e um produto impossível de empacotar. O Gate 0 de `.ablx` vem antes do treino caro.

### 22.6 Apenas recuperação — insuficiente como visão final

É um baseline e uma primeira entrega útil, mas não cobre geração condicional, infilling e variações profundas. Continua parte permanente do sistema híbrido.

## 23. Evidência externa que sustenta a direção

| Projeto/fonte | Evidência útil | Limite |
|---|---|---|
| [Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove) e [GrooVAE](https://proceedings.mlr.press/v97/gillick19a.html) | HVO, velocity/microtiming, dataset e avaliação de grooves humanos | corpus público é muito menor e não resolve integração de produto |
| [MusicVAE configs](https://github.com/magenta/magenta/blob/main/magenta/models/music_vae/configs.py) | baseline reproduzível de 9 vozes e arquitetura latente | stack original não deve ser copiada como runtime moderno sem avaliação |
| [Magenta Studio](https://github.com/magenta/magenta-studio) | prova histórica de UI web local e geração MIDI dentro do fluxo Ableton/Max for Live | arquitetura antiga, não usa Extensions SDK atual |
| [GrooveTransformer](https://github.com/behzadhaki/GrooveTransformer) | Transformer HVO com inferência de baixa latência em instrumento local | licença e empacotamento precisam de revisão; não copiar dependências automaticamente |
| [PocketVAE](https://arxiv.org/abs/2107.05009) | condicionamento por gênero/referência e separação de nota versus expressão | pesquisa, não produto Ableton pronto |
| [Transformer Groove Infilling](https://github.com/pelinski/TransformerGrooveInfilling) | infilling por regiões/vozes e protótipo local de baixa latência | arquitetura/licença/performance precisam ser reproduzidas no nosso ambiente |
| [Ableton MIDI Tools](https://www.ableton.com/en/live-manual/12/midi-tools/) | padrões de UX preview/apply e controles musicais explícitos | ferramentas procedurais, não treinadas no corpus privado |
| [Max for Live MIDI Tools](https://docs.cycling74.com/userguide/m4l/live_miditools/) | mostra limites do ciclo síncrono de transformação MIDI | reforça que inferência assíncrona pesada não deve depender desse caminho |
| [Ableton Extensions SDK](https://www.ableton.com/en/blog/introducing-extensions-sdk/) e [FAQ oficial](https://help.ableton.com/hc/en-us/articles/27303428331420-Ableton-Extensions-FAQ) | base oficial para integração nativa moderna e acesso contextual a clips/tracks/MIDI | beta; a FAQ define ações discretas com pop-up, não painel global persistente nem processamento em background |
| [Playbeat 4](https://audiomodern.com/shop/plugins/playbeat-4/) e [BAZA Drums](https://baza.run/products/detail/drums) | referência de controles, candidatos, locks e variação | arquitetura e treinamento proprietários; servem para UX, não como prova técnica |

## 24. Riscos principais

1. **Extensions SDK beta:** mudanças podem quebrar pacote ou APIs.
2. **Execução do helper incluído:** ainda não foi provada no artefato instalado.
3. **Tamanho do `.ablx`:** modelo + índice + UI podem ultrapassar uma experiência razoável.
4. **Qualidade do corpus:** grande volume pode esconder repetição, weak labels e artefatos.
5. **Memorização:** corpus derivado por algoritmo anterior pode produzir famílias muito próximas.
6. **Mapping de plugins:** SD3 não expõe toda semântica interna de forma confiável pelo Live.
7. **Arrangement:** criar e revalidar alvos pode ser menos seguro que Session.
8. **Portabilidade:** aceleração e assinatura variam por sistema.
9. **Escopo:** catálogo, modelo, Ableton, mappings e embalagem são quatro produtos técnicos; os gates evitam construí-los todos antes de provar valor.
10. **Proveniência autoral:** o corpus está autorizado pela declaração do proprietário, mas lineage do gerador anterior pode estar incompleto; manifests, hashes e limitações precisam permanecer explícitos.
11. **UX modal/contextual:** o SDK atual não prova painel dockado, seleção global observável ou serviço contínuo; a V1 termina ao fechar o modal.

## 25. Decisões finais desta especificação

- O produto é um gerador/navegador de bateria, não um compositor geral.
- O `.ablx` é a única instalação obrigatória.
- A Extension é a ponte real com o Ableton; MCP e Remote Script não são dependências do produto.
- O dashboard web é local, modal e orientado a controles; prompt é secundário.
- O runtime pesado roda em helper isolado e empacotado.
- O sistema é híbrido: catálogo/retrieval + modelo neural + regras de mapping + escritor seguro.
- Drum Rack e presets SD3 explicitamente auditados são os dois alvos iniciais; mapping manual é obrigatório quando a detecção for ambígua.
- O clipe que iniciou a ação contextual pode ser referência, consulta ou base de transformação.
- Candidatos não modificam o projeto até ação explícita.
- O original é preservado por padrão.
- O retriever e os baselines determinísticos precisam ser úteis antes do modelo grande.
- O primeiro challenger é um Transformer condicional/masked sobre projeção HVO + envelope MIDI lossless, não um LLM; o gate escolhe o modelo final.
- O Gate 0 prova a instalação única antes de treinamento pesado.
- Windows x64 é o primeiro alvo; macOS é decisão posterior.
- Nenhum lançamento ou publicação está incluído nesta fase.

## 26. Critério para considerar o conceito consistente

O conceito passa da fase de design quando:

1. uma crítica independente foi executada e toda contradição material ganhou correção, limite explícito ou gate binário;
2. o Gate 0 tem teste executável e critérios binários;
3. o fluxo principal cabe em poucos passos e mantém o Ableton como editor final;
4. busca e geração compartilham a mesma representação canônica;
5. mappings desconhecidos falham de forma explícita e corrigível;
6. a estratégia de split e anti-cópia impede métricas enganosas;
7. cada fase entrega valor observável antes de ampliar o escopo;
8. produção de código começa somente após aprovação explícita desta especificação.

## 27. Resultado da crítica independente

Uma revisão adversarial read-only classificou a primeira versão como **fix-first**: direção plausível, mas com promessas acima do SDK beta. Esta revisão consolidada incorporou os achados materiais:

- painel global persistente virou ação contextual + web modal por invocação;
- seleção global virou objeto/selection capturado e congelado;
- single-install permaneceu requisito duro, porém bloqueado por matriz completa do Gate 0;
- Session slot virou primeiro caminho de escrita; Arrangement permanece fechado até gate próprio;
- writeback ganhou matriz de precondições, receipt, readback e falhas injetadas;
- lifecycle ganhou bind atômico, canal pai privado, parent-death e isolamento por instância;
- Drum Rack foi rebaixado a introspecção parcial e SD3 a presets auditados/perfil manual;
- HVO virou projeção de aprendizado sobre envelope MIDI lossless;
- split passou a considerar lineage, holdout inacessível ao retriever e embedding treinado somente no train;
- Transformer virou challenger, com decoding e alternativas comparáveis;
- pacote/latência ganharam orçamento 1%/10%/100% e P50/P95;
- repetibilidade ficou limitada à mesma matriz de runtime, com resultado canônico para recall exato;
- gates ganharam evidência, thresholds preliminares e autoridade stop/go.

Resoluções adotadas para as perguntas bloqueantes:

1. V1 aceita ação contextual + modal; painel dockado/persistente não é promessa.
2. Se nenhum runtime contido no `.ablx` passar Gate 0, o projeto para e a arquitetura volta ao design; não há instalador separado oculto.
3. Session-only é fallback aceito da V1 até Arrangement passar sua suíte.
4. SD3 começa apenas com presets auditados; seleção manual de perfil é aceitável e segura.
5. O treino pode usar os ~183 mil arquivos declarados autorais pelo proprietário, mas somente depois de manifest, near-dedupe, famílias e splits congelados; fontes futuras continuam fail-closed.
6. Lineage do gerador anterior é desconhecido até auditoria; sua ausência limita alegações de generalização.
7. Repetibilidade significa mesma matriz de modelo/runtime/provider; portabilidade bit-a-bit não é prometida.

**Veredito revisado:** conceito coerente de forma condicional. O valor musical e a arquitetura híbrida são fortes; a viabilidade do produto de instalação única depende primeiro do Gate 0 e não deve ser tratada como concluída.
