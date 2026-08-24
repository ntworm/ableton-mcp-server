# Drum Groove Intelligence — arquitetura e contratos

**Status:** especificação congelada para o gate de aprovação da fase 0
**Data:** 2026-08-20
**Escopo:** corpus MIDI privado no build, runtime offline determinístico, cinco ferramentas MCP e provider neural opcional
**Não é:** implementação, plano de tarefas, varredura de corpus, criação de banco, instalação de dependências ou controle do Ableton Live

## 1. Decisão executiva

Drum Groove Intelligence será um subsistema puro e local do `ableton-mcp-server`.
O runtime recebe um artefato de índice portátil produzido no build e não precisa
conhecer o caminho, o conteúdo ou a existência do corpus privado que o originou.
A execução padrão é determinística: mesmo índice, contrato, algoritmo, entrada e
`seed` produzem o mesmo `artifact_id`, cards e decisões de aplicação em qualquer
máquina compatível.

O corpus privado é apenas uma entrada de build. O build normaliza arquivos MIDI
em uma representação lossless, calcula projeções HVO, features e gramática,
emite proveniência e produz um índice read-only portátil. O pacote portátil pode
conter os payloads lossless autorizados pelo licenciamento; nenhum caminho
absoluto da máquina de build é um requisito de runtime.

O MCP expõe exatamente cinco novas ferramentas compactas:

| Ferramenta | Papel | Efeito |
|---|---|---|
| `groove_search` | localizar candidatos por taxonomia e features | somente leitura |
| `groove_evidence` | explicar um candidato e suas evidências | somente leitura |
| `groove_generate` | gerar um novo artefato a partir de um candidato/condição | grava artefato local; não toca Live |
| `groove_compare` | comparar artefatos por projeções e features | somente leitura |
| `groove_apply` | aplicar um artefato a um slot MIDI explícito | mutação controlada, uma transação Live |

Essas ferramentas retornam `artifact_id`, cards e receipts. Elas nunca retornam
arrays de notas MIDI. A representação lossless fica atrás do repositório de
artefatos e somente o executor interno de `groove_apply` a materializa em
`NoteSpec` para a ponte existente.

O provider neural é uma fronteira separada, opt-in e não obrigatória. O núcleo
determinístico não importa bibliotecas neurais, não baixa modelos e continua
funcional quando o provider está ausente, indisponível ou rejeita a saída. Uma
falha neural aciona fallback determinístico, que fica explícito no card de
geração.

## 2. Contexto atual confirmado

A especificação segue as fronteiras observadas no repositório autorizado:

- `ableton_mcp_server/server.py` instancia FastMCP 3.x, valida requests com
  modelos Pydantic e publica o conjunto ordenado de ferramentas.
- `ableton_mcp_server/models.py` mantém `TOOL_REQUEST_MODELS`; cada ferramenta
  pública precisa de um modelo de request explícito.
- `ableton_mcp_server/catalog.py` é a fonte única de nome, domínio, rota, risco,
  aceitação e reversibilidade. A contagem e a correspondência com o servidor são
  protegidas por testes de catálogo/registro.
- `ableton_mcp_server/music_brain/generators.py` contém hoje um gerador puro de
  bateria e baixo baseado em `random.Random(seed)`, com os eixos
  `electro -> space -> weirdness -> groove` em ordem fixa.
- `ableton_mcp_server/server.py` expõe hoje os wrappers legados
  `music_generate_drum_groove`, `music_generate_bass` e
  `music_plan_production`. Os dois primeiros podem usar `run_batch` para criar
  um clip e inserir notas; o terceiro é local.
- `tests/test_music_brain.py` fixa repetibilidade, limites MIDI, efeitos dos
  quatro eixos e ordem do pipeline. `tests/test_music_tools.py` fixa que a
  geração sem `apply` não chama a ponte, que a aplicação usa `run_batch` e que
  uma falha de batch não é reportada como aplicada.
- A ponte TCP continua loopback-only; mutações não são repetidas depois de
  falha ambígua; `run_batch` agrupa undo, mas não é rollback.

O mapa persistente do target foi consultado como contexto de orientação, mas o
check fresco do `repo-context-loader` retornou `stale` por mudanças em worktrees
de probes. A especificação usa apenas fatos confirmados nos arquivos atuais e
não atualiza o mapa neste trabalho.

### Compatibilidade explícita

Os três wrappers `music_*` existentes permanecem contratos legados e não são
renomeados nem removidos por esta especificação. Seu payload histórico, que pode
conter notas para manter compatibilidade, fica fora da superfície
`groove_*`. Um adaptador futuro pode implementar esses wrappers sobre o novo
engine, mas deve preservar os campos e os limites existentes e só pode ser
aceito com seus testes atuais passando.

As cinco ferramentas novas entram no catálogo como ferramentas locais ou
compostas conforme a tabela de rotas da seção 8. Elas não criam uma rota Live
nova nem removem/alteram semanticamente comandos legados; as únicas extensões
backward-compatible planejadas são o campo opcional de `run_batch` e o campo de
status descritos na seção 10.6. A atualização de contratos vendorizados e da
contagem histórica continua coordenada com seus testes. `groove_apply` reutiliza
somente a ponte e os modelos existentes (`create_clip`, `add_notes_to_clip`,
`run_batch`).

Para proteger o slot sem alterar a rota Live, o modelo de ponte de
`run_batch` terá a extensão backward-compatible `preconditions` opcional,
definida na seção 10.6. Ela não aparece como argumento MCP público:
`groove_apply` a produz internamente e só a envia após negociar a capability;
um `run_batch` legado sem o campo permanece semanticamente compatível com a
ponte que já existe.

## 3. Princípios invariantes

1. **Offline por padrão.** Busca, evidência, geração e comparação funcionam sem
   Live, rede, SQL emitido por um agente ou caminho do corpus privado.
2. **Determinismo observável.** No provider determinístico, toda aleatoriedade
   vem do `seed` solicitado e de um algoritmo versionado. Hora local, locale,
   ordem de diretório, hash nativo do Python, estado global, rede e ordem
   acidental de dicionários não influem. Um provider neural só pode declarar
   determinismo quando sua identidade de modelo, runtime e sampling estiverem
   completas no card; ele não altera o default offline.
3. **Lossless primeiro.** Normalização nunca substitui o MIDI original. Toda
   projeção é derivada, versionada e ligada aos eventos originais por índices de
   track/evento.
4. **Identidade por conteúdo.** Artefatos são endereçados por hash de um
   envelope canônico, não por nome de arquivo, caminho ou índice de consulta.
5. **Cards antes de detalhes.** MCP devolve resumos bounded e ids. Dados raw e
   BLOBs só podem ser lidos pelo repositório interno com limites rígidos.
6. **Taxonomia em facetas.** Estilo, feel, densidade e demais eixos são facetas
   independentes e combináveis; não existe uma árvore exclusiva que obrigue cada
   groove a ter um único pai.
7. **Pitch tardio.** O pitch original sobrevive em todo artefato. Kit mapping é
   uma projeção de aplicação, e todo fallback é declarado.
8. **Mutação explícita.** `groove_apply` exige alvo explícito, não sobrescreve
   slot ocupado e faz no máximo um `run_batch`, sem retry.
9. **Neural isolado.** O provider neural nunca é requisito para instalar,
   indexar, buscar, gerar deterministicamente, comparar ou aplicar.
10. **Proveniência total.** Um card permite identificar corpus/build, versões,
    parent artifacts, transformação, provider, seed e motivo de fallback.

## 4. Fronteiras de componentes

O pacote proposto é `ableton_mcp_server/groove_intelligence/`. Os nomes abaixo
definem responsabilidades; a implementação pode distribuir módulos internos,
mas não pode cruzar estas fronteiras.

| Componente | Responsabilidade | Pode depender de |
|---|---|---|
| `schema` | envelopes, ids, cards e requests versionados | stdlib/Pydantic |
| `canonical` | JSON canônico, hashes, números e ordenação estável | stdlib |
| `midi_lossless` | parse/serialize bounded e eventos lossless | stdlib, parser MIDI aprovado |
| `projections` | HVO, features e gramática derivados | `midi_lossless`, regras versionadas |
| `taxonomy` | facetas multi-eixo e score determinístico | `projections` |
| `index` | adapter read-only para o índice portátil | `schema`, SQL parametrizado |
| `search` | filtros, ranking, cursor e cards | `index`, `taxonomy` |
| `deterministic` | geração, transformações e lineage | `schema`, `projections`, `canonical` |
| `mapping` | kit mapping tardio e relatório de fallback | `midi_lossless`, perfis declarativos |
| `provider` | protocolo abstrato e fallback | `deterministic`, nunca bibliotecas neurais no core |
| `mcp` | wrappers FastMCP e adaptação para a ponte existente | componentes acima, `models`, `catalog`, `server` |

O componente `mcp` não conhece SQL, não abre BLOB diretamente e não acessa o
filesystem do corpus. O adapter `index` recebe uma configuração de índice
read-only do host, não um caminho vindo de request MCP. O componente `mapping`
não altera o artefato fonte; cria um plano derivado com referência ao original.

### Fluxo de dados

```text
corpus privado (build only)
  -> ingestão bounded + proveniência
  -> MidiArtifact lossless
  -> HVO / features / gramática / facetas
  -> índice portátil read-only + seed bundle
                         |
MCP request -> Pydantic -> index/search/deterministic -> cards + artifact_id
                                                        |
                                               mapping tardio
                                                        |
                                          run_batch na ponte (apply only)
```

## 5. Corpus, build e seed portátil

### 5.1 Entrada privada de build

O comando de build recebe uma raiz de corpus explicitamente autorizada pelo
operador. Ele não é uma ferramenta MCP e não é chamado pela skill. A ingestão:

- aceita somente arquivos regulares com extensão MIDI suportada e tamanho máximo
  de 8 MiB;
- resolve symlinks antes da leitura e rejeita um arquivo que escape da raiz
  autorizada;
- rejeita arquivos acima dos limites de tracks/eventos definidos na seção 7;
- ordena entradas pelo `source_digest` SHA-256, nunca pela ordem retornada pelo
  filesystem;
- não grava caminho absoluto, nome de usuário, timestamp de acesso ou conteúdo
  de log no índice;
- exige uma declaração de licença/proveniência para cada item e exclui itens
  sem autorização de redistribuição para o seed bundle;
- registra falhas por digest e motivo em relatório de build, sem interromper
  itens independentes, mas falha o build se o manifesto final não passar os
  gates de integridade.

O build é reprodutível: a identidade da configuração é o hash de um manifesto
canônico contendo lista de inputs, digests, licença normalizada, parser,
normalizer, projeções, taxonomia e limites. Metadados de tempo são excluídos da
identidade; o relatório pode registrar relógio como observação fora do artefato.

### 5.2 Seed portátil

O build produz um `GrooveSeedBundle` versionado, composto por:

1. manifesto JSON canônico com `seed_schema`, `corpus_id`, `build_id`, versões,
   limites e lista ordenada de `artifact_id`;
2. índice SQLite read-only com tabelas descritas na seção 6;
3. payloads lossless comprimidos somente para itens cuja licença permite a
   distribuição e aplicação;
4. relatório de proveniência sem caminhos locais;
5. checksum SHA-256 de cada arquivo, `logical_index_digest` e um
   `bundle_manifest_digest` calculado a partir das entradas ordenadas (sem
   depender de timestamps ou layout físico do SQLite).

Um seed pode ser copiado para outra máquina e aberto sem o corpus original.
Itens que não podem carregar payload lossless por licença podem permanecer no
índice apenas como cards de busca/evidência, com
`capabilities.apply=false`; o card deve declarar esse fato. O build nunca
finge que um payload ausente é aplicável.

O seed bundle não é o `seed` numérico de uma geração. O primeiro é um artefato
portátil de dados; o segundo é entrada explícita do algoritmo. Para evitar
confusão, o contrato usa `seed_bundle_id` para o primeiro e `seed` para o
segundo.

### 5.3 Licenciamento e proveniência

Cada card e cada linha de artefato carregam:

- `corpus_id` e `build_id` content-addressed;
- `source_digest` e `source_kind` anonimizados;
- `license_id` e `redistribution` (`full`, `derived_only`, `blocked`);
- `importer_id`, `normalizer_id` e suas versões;
- `provenance_digest`, hash do registro de origem canônico;
- `parent_artifact_ids` para derivados.

`source_path` nunca atravessa o build boundary. Um registro sem licença válida
é rejeitado antes de entrar no seed.

### 5.4 Lattice de direitos e capabilities

Direitos formam uma ordem conservadora, não um conjunto de booleans
independentes:

| `rights_level` | Nome | Permite |
|---:|---|---|
| 0 | `blocked` | nenhum card operacional; item é omitido do seed |
| 1 | `derived_only` | busca, evidência e geração de derivados sem payload redistribuível |
| 2 | `full` | busca, evidência, geração e aplicação quando o payload está presente |

O nível efetivo de um artefato derivado é o menor nível entre todos os pais,
o nível autorizado pela operação e o nível autorizado pelo perfil de mapping.
Essa operação é um `meet`, nunca uma promoção: `full -> derived_only` é
permitido, `derived_only -> full` não. Um parent omitido, desconhecido,
`blocked` ou sem proveniência válida torna o derivado `blocked` e impede sua
publicação.

`capabilities` é calculado, não confiado ao request:

- `search` e `evidence` exigem `rights_level >= derived_only`;
- `generate` exige `rights_level >= derived_only`, grava todos os parents e
  nunca copia um payload proibido para o derivado;
- `apply` exige `rights_level == full`, `payloads.blob` presente, license
  `redistribution=full` e mapping profile permitido;
- `compare` pode operar sobre cards `derived_only`, mas não cria capacidade
  nova;
- um provider neural não pode elevar rights nem omitir parent ids.

Cada bloqueio carrega `capability=false` e um motivo enum (`rights_blocked`,
`parent_rights_blocked`, `payload_not_redistributable`, `license_missing`,
`mapping_not_authorized`). O MCP não oferece override para esses motivos.

### 5.5 Estratégia de parser e dependências

O parser de SMF e o serializer usados pelo subsistema são internos e versionados
como `smf-parser-v1` e `smf-serializer-v1`. Eles usam somente a biblioteca
stdlib do Python suportado pelo repositório (`hashlib`, `json`, `struct`,
`zlib`, `sqlite3`, `unicodedata` e `decimal`); não há dependência MIDI opcional,
download ou instalação implícita. O parser valida header, track chunks, VLQ,
running status, meta, sysex, note pairs e limites antes de emitir a tabela de
eventos, preservando os bytes originais para o hash. O serializer canônico é
usado apenas para artefatos gerados e tem uma versão própria no envelope.

Trocar parser, serializer, Python mínimo, codec ou versão de SQLite exige novo
`normalizer_id`/`algorithm_versions`, novo digest de build e revisão desta
especificação; não é uma atualização transparente. O runtime produtivo não
instala bibliotecas para abrir um seed.

## 6. Artefatos e esquema persistente

### 6.1 Identidade e serialização

Um `artifact_id` é `ga1_` seguido por 64 caracteres hexadecimais SHA-256. A
preimage é exatamente:

```text
ASCII("ABLETON-GROOVE-ARTIFACT-V1") || BYTE(0x00)
|| UTF8(canonical_json(identity_preimage))
```

`identity_preimage` é um objeto canônico UTF-8 com chaves ordenadas,
separadores compactos, números finitos e inteiros MIDI/tick quando a unidade
permitir. Ele contém `schema_version`, `kind`, `format`, `timing`, `tracks`,
`payload_sha256`, `events_digest`, todos os `projection_digests`,
`provenance_digest` e `lineage_digest`. O objeto não contém `artifact_id`,
`request_id`, nome de arquivo, ordem de query, timestamp de execução ou
pretty-print. Assim, o id não é autorreferente e não pode mudar por ser escrito
no próprio envelope.

O envelope armazenado repete o `artifact_id` calculado e deve ser rejeitado se
qualquer digest citado na preimage não conferir com o payload/projeção/lineage
real. Para uma origem, `payload_sha256` é o SHA-256 dos bytes SMF exatos; para
um derivado, é o SHA-256 da serialização lossless canônica produzida pelo
generator, sem incluir o próprio id. `events_digest`, `projection_digests`,
`provenance_digest` e `lineage_digest` também são calculados sobre objetos que
excluem o id do artefato; lineage usa somente a lista ordenada de parent ids,
relations e ordinals. O domínio e todos os digests fazem parte do hash; não
existe forma alternativa de calcular o mesmo id.

`request_hash` tem um contrato próprio e não inclui o cursor de paginação. Para
qualquer request já validado e normalizado, a preimage é exatamente:

```text
ASCII("ABLETON-GROOVE-REQUEST-V1") || BYTE(0x00)
|| UTF8(canonical_json(request_for_hash))
```

`request_for_hash` contém `schema_version`, todos os campos que influenciam o
resultado, defaults efetivos e, quando aplicável, `ranker_id` e
`ranker_manifest_digest`. Em `groove_search`, a lista exata é
`schema_version`, `query`, `facets`, `feature_constraints`, `bpm`, `meter`,
`seed_bundle_id`, `required_projection_ids`, `projection_operator`, `limit`,
`ranker_id` e `ranker_manifest_digest`. O campo `cursor` é excluído
explicitamente, inclusive quando está presente ou é `null`; nenhum outro campo
desconhecido chega ao hash. Portanto, a página 2 calcula o mesmo
`request_hash` da página 1 e o compara com o valor carregado no cursor.

`canonical_json` é definido sem depender de pretty-print: strings são NFC,
objetos têm chaves ordenadas por valor Unicode codepoint após NFC, arrays
preservam ordem salvo onde o schema declara conjunto sem ordem, os arrays de
`facets` e `required_projection_ids` são deduplicados e ordenados, e
`feature_constraints` é ordenado pelo seu próprio JSON canônico. Números são
inteiros ou decimais finitos; features e limites decimais são quantizados a
nove casas, sem expoente e sem `-0.0`. A serialização usa UTF-8, `ensure_ascii`
desligado, separadores `,` e `:`, sem whitespace, escapes JSON mínimos para
controle/aspas e `allow_nan=false`. Ausência e default explícito são
normalizados para o mesmo objeto antes da serialização. O resultado de
`request_hash` é o SHA-256 em hex minúsculo de 64 caracteres.

O `reproducibility_key` é SHA-256 de:

```text
schema_versions || seed_bundle_id || algorithm_versions || canonical_request
|| parent_artifact_ids || provider_identity
```

Strings são UTF-8 NFC; `-0.0`, NaN e infinito são inválidos. Floats de features
são serializados com 9 casas decimais depois de validação de finitude. Ticks,
velocidade MIDI, canal, pitch e flags são inteiros.

### 6.2 `MidiArtifactV1` lossless

O envelope conceitual é:

```json
{
  "schema_version": "groove.midi-artifact.v1",
  "artifact_id": "ga1_<sha256>",
  "kind": "source|generated|mapped",
  "format": {"smf_type": 0, "ppq": 480, "track_count": 2},
  "timing": {"length_ticks": 7680, "meters": [], "tempos": []},
  "tracks": [
    {
      "track_index": 0,
      "name": "Drums",
      "events_digest": "sha256",
      "event_count": 128
    }
  ],
  "payload": {
    "codec": "zlib-raw-midi-v1",
    "raw_size": 4096,
    "compressed_size": 1200,
    "sha256": "sha256"
  },
  "provenance": {},
  "lineage": {},
  "projections": {}
}
```

O payload raw preserva todos os bytes do SMF válido. A tabela lógica de eventos,
derivada durante ingestão, preserva para cada evento:

- `track_index`, `event_index` e `channel` quando aplicável;
- `delta_ticks` e `absolute_ticks` sem arredondamento;
- tipo MIDI/meta/sysex e payload de bytes codificado no envelope;
- para pares note-on/note-off, `note_event_id`, pitch original, velocidade,
  início, duração, canal e ordem de encerramento;
- eventos não musicais, mudanças de programa, CC, aftertouch, pitch bend,
  tempo, métrica, armadura, markers e sysex, mesmo quando não entram em uma
  projeção.

Um parser pode acrescentar índices derivados, mas nunca descarta evento que
estava no arquivo. Ao reserializar, o hash do payload original deve continuar
igual para artefatos de origem. Se o formato não puder ser interpretado dentro
dos limites, o item não entra no índice.

### 6.3 Projeções versionadas

As projeções são independentes do payload e podem ser atualizadas sem fingir que
o MIDI mudou. Cada projeção registra seu próprio `projection_schema` e
`source_events_digest`.

#### HVO: Hit, Velocity, Offset

HVO é uma grade analítica, não a fonte lossless:

```json
{
  "schema_version": "groove.hvo.v1",
  "grid_ticks": 120,
  "roles": ["kick", "snare", "closed_hat", "open_hat", "other"],
  "cells": [
    {
      "role": "snare",
      "bar": 0,
      "step": 6,
      "hit": 1,
      "velocity": 0.82,
      "offset_ticks": -3,
      "event_ids": [17]
    }
  ]
}
```

`hit` é 0/1, `velocity` é velocidade original normalizada em `[0,1]` e
`offset_ticks` é a diferença assinada entre o evento original e o grid mais
próximo. A projeção nunca altera o evento e não pode representar duas notas
distintas como uma única nota sem manter todos os `event_ids`.

#### Features

`groove.features.v1` contém apenas valores determinísticos e nomes estáveis:

- contexto: `bars`, `beats`, `meter`, `ppq`, `tempo_min`, `tempo_max`;
- densidade: hits por bar, hits por role, ocupação por subdivisão;
- dinâmica: média, desvio, quantis e contraste de velocity;
- tempo: média, desvio e histograma de `offset_ticks`;
- feel: swing estimado, syncopation, accent alignment, microtiming;
- forma: repetição de célula, entropia de transição e polifonia;
- duração: média, mediana e proporção de sobreposição;
- cobertura: roles presentes, faixas de pitch e eventos não projetados.

Cada valor tem `unit`, `algorithm_version` e `validity`; uma feature não
calculável recebe `status="unavailable"` em vez de zero inventado.

#### Gramática

`groove.grammar.v1` é um conjunto de tokens e transições bounded para análise e
geração determinística:

- token = `{role, grid_step, velocity_bin, offset_bin, duration_bin}`;
- uma janela nunca cruza a fronteira de `bars` declarada;
- transições contam apenas eventos realmente presentes e usam normalização
  Laplace fixa `alpha=1`;
- o índice guarda top transitions por frequência, com desempate lexical;
- nenhum token remove ou reescreve evento lossless.

Gramática é uma projeção opcional: cards declaram `projection_status` e a versão
da gramática usada. Ausência de gramática não invalida HVO ou features.

### 6.4 Índice read-only

O banco conceitual é SQLite v1 em modo somente leitura e immutable, criado
somente no build; esta especificação não cria um banco real. O DDL mínimo abaixo
é executável em SQLite 3.40+ e é a fonte do schema lógico:

```sql
PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE index_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('source', 'generated', 'mapped')),
  corpus_id TEXT NOT NULL,
  build_id TEXT NOT NULL,
  license_id TEXT NOT NULL,
  redistribution TEXT NOT NULL
    CHECK (redistribution IN ('full', 'derived_only', 'blocked')),
  rights_level INTEGER NOT NULL CHECK (rights_level BETWEEN 0 AND 2),
  capabilities_json TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  payload_size INTEGER NOT NULL CHECK (payload_size >= 0),
  payload_sha256 TEXT NOT NULL,
  events_digest TEXT NOT NULL,
  provenance_digest TEXT NOT NULL,
  lineage_digest TEXT NOT NULL
);
CREATE TABLE facets (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  axis TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
  PRIMARY KEY (artifact_id, axis, value)
);
CREATE TABLE features (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  value REAL,
  unit TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('available', 'unavailable')),
  PRIMARY KEY (artifact_id, name, version),
  CHECK (status = 'unavailable' OR value IS NOT NULL)
);
CREATE TABLE feature_norms (
  ranker_id TEXT NOT NULL,
  feature_name TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  min_value REAL NOT NULL,
  max_value REAL NOT NULL,
  PRIMARY KEY (ranker_id, feature_name, feature_version),
  CHECK (max_value > min_value)
);
CREATE TABLE projections (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  digest TEXT NOT NULL,
  codec TEXT NOT NULL CHECK (codec IN ('zlib-raw-json-v1')),
  blob BLOB NOT NULL,
  raw_size INTEGER NOT NULL CHECK (raw_size >= 0),
  compressed_size INTEGER NOT NULL CHECK (compressed_size >= 0),
  PRIMARY KEY (artifact_id, name, version)
);
CREATE TABLE payloads (
  artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
  codec TEXT NOT NULL CHECK (codec IN ('zlib-raw-midi-v1')),
  blob BLOB,
  raw_size INTEGER NOT NULL CHECK (raw_size >= 0),
  compressed_size INTEGER NOT NULL CHECK (compressed_size >= 0),
  sha256 TEXT NOT NULL,
  CHECK (blob IS NOT NULL OR raw_size = 0)
);
CREATE TABLE lineage (
  artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  parent_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
  relation TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (artifact_id, parent_artifact_id, relation, ordinal)
);
CREATE TABLE provenance (
  artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
  provenance_digest TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  license_id TEXT NOT NULL,
  redistribution TEXT NOT NULL
    CHECK (redistribution IN ('full', 'derived_only', 'blocked'))
);

CREATE INDEX facets_lookup ON facets(axis, value, artifact_id);
CREATE INDEX features_lookup ON features(name, version, value, artifact_id);
CREATE INDEX lineage_parent_lookup ON lineage(parent_artifact_id, artifact_id);
CREATE INDEX projections_lookup ON projections(artifact_id, name, version);
```

`index_meta` deve conter, no mínimo, `schema_version=groove.index.v1`,
`seed_bundle_id`, `build_id`, `manifest_digest`, `logical_index_digest`,
`ranker_id`, `ranker_manifest_digest`, `normalizer_id`, `projection_versions`
e `sqlite_min_version=3.40`. O `user_version` deve ser `1`; o runtime rejeita
qualquer outro valor ou uma ausência de chave obrigatória.

`artifact_id`, `axis`, `value`, `name` e demais valores vêm sempre como bind
parameters. Nenhuma query é montada por concatenação de request, nome de tabela
ou SQL recebido do cliente. O adapter usa um conjunto fechado de statements
versionados, conexão `file:<absolute-index>?mode=ro&immutable=1` com URI mode
ativado, `PRAGMA query_only=ON` e `PRAGMA foreign_keys=ON`; falha se schema,
manifest digest, `user_version` ou modo da conexão não corresponder ao manifesto.

Migrações não ocorrem no runtime. Um schema futuro recebe `user_version=2` e um
novo `groove.index.v2`; o builder lê v1, escreve um novo bundle v2 e publica um
manifesto novo. O runtime v1 rejeita v2 com `GROOVE_SCHEMA_UNSUPPORTED`.

O resultado de busca lê colunas de card e features. O BLOB de payload só é lido
depois de uma resolução exata por `artifact_id`, capability check e validação de
tamanho. A skill não executa SQL nem lê BLOBs.

O arquivo SQLite pode variar em bytes por versão de SQLite, page size ou
vacuum. O gate de reprodutibilidade compara `logical_index_digest`: SHA-256 do
manifesto, de todas as linhas não-meta, colunas e BLOB digests ordenados pela
chave primária e serializados em canonical JSON. O cálculo exclui as chaves
auto-referentes `index_meta.logical_index_digest`, `manifest_digest` e
`bundle_manifest_digest`; depois de calcular, o builder grava esses valores e
o `bundle_manifest_digest`. Os payload/projection digests,
`artifact_id`s e cards devem ser iguais; byte-identidade do arquivo não é uma
promessa. Um build pode fixar SQLite 3.40+, page size e vacuum para reduzir
variação, mas a aceitação usa o digest lógico.

## 7. Limites e defesa do índice

Os limites são parte do contrato, não ajustes de configuração silenciosos:

| Recurso | Limite |
|---|---:|
| arquivo MIDI de entrada | 8 MiB |
| tracks por arquivo | 256 |
| eventos por arquivo | 1.000.000 |
| barras de geração | 1–64 |
| eventos materializados por clip e chamada Live | 2.048 |
| BLOB comprimido retornado pelo adapter | 8 MiB |
| BLOB descomprimido | 32 MiB |
| razão descomprimido/comprimido | 100:1 |
| itens por `groove_search` | 1–50, default 20 |
| constraints de feature por busca | 32 |
| `artifact_ids` em compare | 2–8 |
| facets por eixo | 32 |
| eixos por request | 16 |
| tamanho serializado de um card | 64 KiB |
| orçamento agregado de resposta MCP | 512 KiB (524.288 bytes) |
| duração de uma consulta index | 250 ms |

O decoder usa `zlib.decompressobj` em chunks e interrompe ao ultrapassar tamanho
ou razão; não chama `decompress` sem limite. Verifica checksum, bytes finais,
codec permitido e `raw_size` declarado. BLOB malformado, excesso de memória,
schema incompatível, hash divergente e payload truncado são erros explícitos.
Nenhum limite é ampliado a partir de um campo MCP.

O runtime não aceita caminho de payload no request, URI arbitrária, SQL, pickle,
execução de código, arquivo temporário controlado pelo cliente ou importação de
um corpus. O host escolhe um único seed bundle configurado e o abre em modo
read-only.

### 7.1 Orçamento agregado de resposta MCP

O orçamento é medido pelo builder de envelope como a soma, em bytes UTF-8, do
JSON compacto de `structured_content`, de cada `TextContent.text` e dos campos
JSON adicionais que o wrapper realmente envia. O limite inclui overhead do
envelope lógico, é aplicado antes de FastMCP escrever no transporte e vale para
sucesso, truncamento e erro. Um wrapper não pode emitir uma segunda cópia sem
contabilizá-la.

Limites individuais para tornar o orçamento implementável são: `ArtifactCardV1`
6 KiB; `EvidenceCardV1` 32 KiB; `GenerationCardV1` 16 KiB; `CompareCardV1`
128 KiB; `ApplyReceiptV1` 32 KiB; erro 8 KiB. Esses limites são máximos, não
reservas; o builder calcula o tamanho real.

`groove_search` aceita `limit` de 1 a 50. Ele ordena candidatos primeiro, tenta
adicionar cada card nessa ordem e para antes do próximo que excederia 524.288
bytes. A resposta inclui `returned_count`, `omitted_count`,
`truncated=true|false` e um `next_cursor` apontando exatamente para o primeiro
item omitido. Assim, `limit=50` continua válido mesmo quando somente parte cabe
no orçamento. Se o envelope mínimo não couber, retorna
`GROOVE_RESPONSE_BUDGET_EXCEEDED` sem cards.

`groove_evidence` trunca contribuições e referências por ordem de impacto e
digest, marcando `truncated`; `groove_compare` reduz detalhes opcionais dos
cards, mas preserva ids, matriz e estado de compatibilidade. Se o esqueleto
mínimo de qualquer uma delas não couber, falha com o mesmo código. Geração e
aplicação falham deterministicamente quando seu receipt mínimo não couber.
Truncamento nunca altera score, ids, estado de aplicação ou conteúdo lossless.

## 8. Taxonomia multi-eixo e pitch mapping tardio

### 8.1 Facetas

Cada artifact card pode ter múltiplos valores em cada eixo. Os eixos normativos
são:

| Eixo | Valores ou medida |
|---|---|
| `style` | tags de estilo autorizadas pelo corpus |
| `feel` | straight, swung, laid_back, pushed, mixed |
| `density` | `sparse`, `medium`, `dense` + `hits_per_bar` |
| `syncopation` | `low`, `medium`, `high` + score |
| `energy` | `low`, `medium`, `high` + score |
| `complexity` | `low`, `medium`, `high` + entropia |
| `microtiming` | `tight`, `human`, `loose` + distribuição |
| `meter` | numerador/denominador |
| `tempo` | faixa BPM e confiança |
| `kit` | roles/kit de origem, sem reescrever pitch |
| `era` | tag de proveniência, não inferência biográfica |
| `license` | full, derived_only, blocked |

`style`, `era` e outros labels editoriais são entradas declaradas ou regras
versionadas; nunca são inventados por um provider neural no runtime. Filtros
fazem AND entre eixos e OR dentro de um eixo. Não há uma árvore
`style -> substyle ->` que exclua labels válidos em outros eixos.

O ranker fixo é `groove-ranker-v1`, com manifesto e digest no índice. Sua score
usa pesos racionais imutáveis: `text=20/100`, `facets=25/100`,
`features=40/100` e `projection_coverage=15/100`. Feature missing não vira
zero: se uma constraint exigir a feature, o item não casa; sem constraint, o
componente recebe `0.0` e o card declara a ausência. Scores são quantizados a
9 casas antes da ordenação; empate usa `artifact_id` ascendente.

`groove_search` aceita `required_projection_ids`, lista opcional de no máximo
três ids únicos dentre `groove.hvo.v1`, `groove.features.v1` e
`groove.grammar.v1`, e `projection_operator`, enum `all|any` com default
`all`. O operador é uma regra de elegibilidade: `all` mantém somente cards que
tenham todas as projeções listadas e `any` mantém cards que tenham pelo menos
uma; projeção presente mas inválida também conta como ausente. O componente
`projection_coverage` calcula, antes da elegibilidade, o número de projeções
presentes e válidas dividido pelo número solicitado. Assim, para `all` ele é
1.0 nos candidatos elegíveis e, para `any`, conserva informação de cobertura
parcial. A lista vazia desativa completamente esse componente — disponibilidade
de projeção não afeta a ordem — e renormaliza os restantes por divisão exata
pela soma `85/100`: `text=4/17`, `facets=5/17` e `features=8/17`. O manifesto e
o response `ranking` registram `projection_coverage_active` e os pesos efetivos
quantizados a 9 casas; não há arredondamento dependente da ordem dos campos.

O componente `text` tokeniza `query` após NFC, lowercase Unicode, remoção de
pontuação e whitespace determinístico; score é Jaccard entre tokens da query e
tokens de labels/roles do card. `facets` é a fração de valores pedidos que
casam exatamente. `features` é `1 - média` das distâncias normalizadas dos
constraints pedidos; sem constraints vale `0.0`. Quando
`required_projection_ids` não é vazio, `projection_coverage` é a fração de
HVO/features/grammar presentes e válidas entre os ids solicitados. Quando a
lista é vazia, o componente é removido da soma, em vez de receber `0.0`, e os
três pesos restantes são os renormalizados acima. A fórmula e a decisão de
elegibilidade não mudam conforme a ordem de entrada; o manifesto registra os
casos `all`, `any` e conjunto vazio.

O ranker normaliza cada feature por `(value-min)/(max-min)`, clamp em `[0,1]`,
com `min_value`/`max_value` fixos na tabela `feature_norms` e presos ao
`ranker_manifest_digest`. Operadores de constraint são exatamente `eq`, `lt`,
`lte`, `gt`, `gte`, `between` (intervalo inclusivo) e `in`; operandos precisam
da mesma unidade e faixa declarada, ou o request falha. A distância de `eq` é
`abs(value-target)` normalizada; `lt`/`lte` e `gt`/`gte` medem somente a
violação, `between` mede distância ao intervalo e `in` usa a menor distância
entre candidatos. Match booleano exige distância zero. O caller não fornece
pesos arbitrários; mudar pesos exige novo `ranker_id` e schema de cursor.

O cursor usa payload canônico com `schema_version` igual a
`groove.search.cursor.v1`, `seed_bundle_id`, `logical_index_digest`, `ranker_id`,
`ranker_manifest_digest`, `request_hash`, `limit`, `last_score` e
`last_artifact_id`. Seja `payload_bytes` o UTF-8 desse JSON canônico; o token
exato é `base64url_no_pad(payload_bytes || checksum)`, onde
`checksum = SHA256(ASCII("ABLETON-GROOVE-CURSOR-V1") || BYTE(0x00) ||
payload_bytes)`. O decoder rejeita padding, JSON não canônico, payload acima
de 4 KiB ou checksum incorreto com `GROOVE_CURSOR_INVALID`; compara o checksum
em tempo constante sobre os 32 bytes crus. Depois valida todos os campos e
compara os 32 bytes decodificados do `request_hash` do cursor em tempo
constante com os 32 bytes do hash calculado do request sem `cursor`; digest que
não seja hex minúsculo de 64 caracteres produz `GROOVE_CURSOR_INVALID`, e
divergência produz `GROOVE_CURSOR_QUERY_MISMATCH`, nunca
reinicia silenciosamente. Isso também rejeita cursor de outra query, bundle,
ranker, schema ou page size. A página seguinte começa estritamente depois do
par `(last_score,last_artifact_id)`; não há cursor que dependa de relógio.

### 8.2 Mapping

O mapping só ocorre na geração derivada ou imediatamente antes de aplicar. O
artefato fonte sempre conserva `original_pitch` e `original_channel`.

Um `KitMappingProfileV1` contém `profile_id`, `profile_version`, regras em ordem
determinística, `on_unmapped` (`reject` por padrão ou `skip`) e fallback
explícito. Cada evento mapeado produz internamente:

```json
{
  "event_id": 17,
  "original_pitch": 49,
  "original_channel": 9,
  "resolved_pitch": 46,
  "resolved_role": "open_hat",
  "method": "exact|role|gm_fallback|user_override|unmapped",
  "fallback": false,
  "warning": null
}
```

A ordem de resolução é: `user_override` exato; mapeamento exato do perfil;
role reconhecida pela metadata/HVO; mapa GM declarado pelo perfil; fallback por
role configurado. Se nada resolver, `resolved_pitch=null`,
`method="unmapped"`, `fallback=true`. Com `on_unmapped="reject"`, preview e
commit falham antes de tocar Live; com `on_unmapped="skip"`, o evento não é
aplicado e o receipt declara a contagem. O sistema nunca troca silenciosamente
um pitch. O card de geração e o receipt de aplicação contêm contagens de
exact/fallback/unmapped e o limite máximo de avisos, sem expor a lista de notas.

Por padrão o perfil `gm-drums-v1` é permitido apenas para canal 10/índice 9 e
declara seus números. Um perfil de kit não pode alterar `artifact_id` do pai;
um artefato `kind="mapped"` recebe novo id com lineage.

## 9. Cards e envelopes

Todos os envelopes novos têm `schema_version`, `request_id` opcional,
`artifact_id` quando aplicável, `reproducibility_key`, `warnings` bounded e
`provenance`. O conteúdo abaixo é conceitual e normativo quanto aos nomes;
campos opcionais são omitidos, não serializados como `null` quando o contrato
determinar ausência.

### 9.1 `ArtifactCardV1`

```json
{
  "schema_version": "groove.card.artifact.v1",
  "artifact_id": "ga1_<sha256>",
  "kind": "source|generated|mapped",
  "summary": {
    "bars": 4,
    "meter": "4/4",
    "bpm_range": [118.0, 124.0],
    "roles": ["kick", "snare", "closed_hat"]
  },
  "facets": {"feel": ["laid_back"], "density": ["medium"]},
  "features": {"hits_per_bar": 12.0, "syncopation": 0.31},
  "projections": {"hvo": "groove.hvo.v1", "grammar": "groove.grammar.v1"},
  "rights_level": "full",
  "capabilities": {
    "evidence": {"allowed": true},
    "generate": {"allowed": true},
    "apply": {"allowed": true}
  },
  "provenance": {"corpus_id": "...", "build_id": "...", "license_id": "..."}
}
```

### 9.2 `EvidenceCardV1`

Inclui `artifact_id`, `query_hash`, `matched_facets`, até 32 contribuições de
feature ordenadas por impacto, projection digests, provenance digest,
`limitations` e `confidence`. Uma contribuição é `{name, requested, observed,
weight, distance}`. Não inclui raw event/BLOB.

### 9.3 `GenerationCardV1`

Inclui `artifact_id`, `parent_artifact_ids`, `generator_id/version`,
`transforms` multi-eixo, `seed`, `provider_requested`, `provider_resolved`,
`fallback` (`false` ou `{reason, deterministic_provider}`), resumo, mapping
summary, `deterministic` (booleano) e `reproducibility_key`. O valor é sempre
`true` no provider determinístico; no provider neural só é `true` quando os
gates de identidade e repetibilidade da seção 12 forem satisfeitos.

### 9.4 `CompareCardV1`

Inclui `artifact_ids`, `metric_schema`, matriz de distâncias, diferenças por
faceta/eixo, compatibilidade de PPQ/meter, `common_projections`, lineage e
limitações. A matriz é bounded a oito ids e não contém eventos.

### 9.5 `ApplyReceiptV1`

Inclui `artifact_id`, `target` (`track_index`, `clip_index`), `mode` (`preview`
ou `commit`), `state`, `bridge_stage`, `clip_ref`, `counts`, `mapping_summary`,
`bridge_status`, `undo_group`, `recovery`, `warnings`, `reproducibility_key` e
erro estruturado quando houver. Não inclui `notes`, `payload`, BLOB ou lista de
eventos.

Os estados normativos são `preview`, `rejected`, `committed`, `partial` e
`unknown`:

| Estado | Significado | `recovery.action` |
|---|---|---|
| `preview` | validação local completa; nenhum comando Live enviado | `none` |
| `rejected` | validação, direitos, mapping, precondition ou slot ocupado recusou antes do write | corrigir request/slot |
| `committed` | create e add confirmados pelo batch | `user_undo_available` |
| `partial` | prefixo do batch confirmou create, mas add falhou ou confirmou contagem menor | inspecionar e desfazer/limpar com ação do usuário |
| `unknown` | transporte/protocolo falhou depois do envio e o estado Live é ambíguo | inspecionar antes de qualquer retry |

`bridge_stage` é `none`, `precondition`, `create_clip`, `add_notes_to_clip`,
`batch_complete` ou `transport_after_send`. `counts` sempre contém
`requested`, `selected`, `mapped`, `unmapped`, `skipped`, `sent` e
`confirmed`; `confirmed` é `null` em `unknown`, nunca zero inventado. `clip_ref`
contém `track_index`, `clip_index`, `created` (`true|false|unknown`) e
`length_beats`. `recovery` contém `automatic_retry=false`, a ação acima e a
razão estruturada. Um resultado `partial` não promete atomicidade: o `run_batch`
é um agrupamento de undo, não rollback. Qualquer chunking multi-call futuro
precisará de novo contrato e não poderá ser descrito como atomicidade.

### 9.6 Materialização no Live atual

O caminho existente aceita `NoteSpec` sem canal e limita
`add_notes_to_clip.notes` a 2.048 itens. Portanto `groove_apply` escreve um
único clip em um único `track_index`; não existe aplicação multi-track no v1.
Um artefato com mais de uma track ou mais de um canal precisa de
`source_track_index` e `source_channel` explícitos para selecionar uma única
faixa/canal. Sem esses seletores, o request falha com
`GROOVE_APPLY_SCOPE_REQUIRED`. Depois da seleção, `gm-drums-v1` exige o canal
9 (MIDI channel 10, zero-based) e falha com
`GROOVE_APPLY_CHANNEL_UNSUPPORTED` nos demais canais. `native-compatible`
aceita o único canal selecionado e preserva os pitches exatamente, porque o
destino já fornece o mapeamento nativo do kit. Não há descarte silencioso de
canais.

O conversor usa PPQ do `MidiArtifactV1`: `start_beats = absolute_ticks / ppq` e
`duration_beats = duration_ticks / ppq`, porque um beat Live é uma semínima
independentemente do denominador da métrica. O cálculo usa inteiros/racionais
até a borda MCP e arredonda half-even a 9 casas decimais; `ppq <= 0`, duração
zero ou resultado fora de `[0,100000]` falha. O comprimento do clip é o teto
bounded do maior `end_beats`, também serializado a 9 casas.

O limite de 2.048 vale para a seleção inteira de uma chamada/clip. Se o artifact
selecionado exceder esse limite, `preview` retorna `rejected` e `commit` não
abre undo; o sistema não divide a operação em chamadas sucessivas. Qualquer
chunking futuro será uma versão independente com receipts por chamada e sem
promessa de atomicidade.

## 10. As cinco ferramentas MCP

### 10.1 `groove_search`

**Request `groove.search.request.v1`:**

```json
{
  "schema_version": "groove.search.request.v1",
  "query": "laid back kick snare",
  "facets": {"feel": ["laid_back"], "density": ["medium"]},
  "feature_constraints": [
    {"name": "syncopation", "op": "between", "value": [0.2, 0.6]}
  ],
  "bpm": [110.0, 130.0],
  "meter": "4/4",
  "seed_bundle_id": "optional exact bundle pin",
  "required_projection_ids": ["groove.hvo.v1"],
  "projection_operator": "all",
  "limit": 20,
  "cursor": "opaque"
}
```

`query` é texto para token matching determinístico e limitado; não é prompt
para LLM. `facets`, `feature_constraints` e `required_projection_ids` são
opcionais, mas o request deve conter pelo menos um critério entre eles, `query`,
`bpm` e `meter`. O resultado é
`groove.search.response.v1` com `items: ArtifactCardV1[]`, `total_hint`,
`returned_count`, `omitted_count`, `truncated`, `next_cursor`, `ranking` (pesos
e algoritmo) e `provenance`. `limit=0` não é aceito; cursor inválido falha em
vez de reiniciar silenciosamente. `truncated=true` só ocorre por orçamento MCP
e sempre traz cursor para continuação; score e ordem da próxima página não
mudam.

### 10.2 `groove_evidence`

**Request `groove.evidence.request.v1`:** `{schema_version, artifact_id,
query_hash?, include_projections:[hvo,features,grammar]}`. Sem `query_hash`, a
resposta explica o artefato isoladamente; com ele, explica a mesma busca que
originou o card. A resposta `groove.evidence.response.v1` contém um
`ArtifactCardV1`, um `EvidenceCardV1` e no máximo 32 referências de evento
agregadas por role/grid; referências são contagens/digests, nunca notas ou
payload.

### 10.3 `groove_generate`

**Request `groove.generate.request.v1`:**

```json
{
  "schema_version": "groove.generate.request.v1",
  "source": {"artifact_id": "ga1_<sha256>"},
  "transforms": {
    "density": 0.2,
    "syncopation": -0.1,
    "swing": 0.4,
    "microtiming": 0.1,
    "energy": 0.0,
    "complexity": 0.3
  },
  "bars": 4,
  "seed": 7,
  "provider": "deterministic|neural"
}
```

`source` aceita exatamente um `artifact_id` ou um `search` inline equivalente
a `groove_search` com `limit=1`; o resultado fixa o parent id no lineage. Cada
transformação é um eixo independente em `[-1,1]`, com semântica definida pela
versão do generator. Eixos desconhecidos falham explicitamente. Pitch e kit
mapping continuam intocados nesta etapa; a projeção `mapped` só é criada no
`groove_apply`. `provider` default é `deterministic`; `neural` é apenas uma
preferência, nunca uma exigência do sistema.

O response `groove.generate.response.v1` contém um `GenerationCardV1` e o
`ArtifactCardV1` do novo artefato. O artefato é materializado no store local de
resultados antes da resposta; repetição com a mesma chave retorna o mesmo
artefato, sem duplicata.

### 10.4 `groove_compare`

**Request `groove.compare.request.v1`:** `{schema_version, artifact_ids[2..8],
metrics:[facets,features,hvo,grammar], normalize:true}`. Todos os ids devem
estar no mesmo seed ou carregar projeções compatíveis; caso contrário o
resultado declara incompatibilidade e não inventa distância. O response contém
`CompareCardV1` e cards dos itens, nunca os payloads.

### 10.5 `groove_apply`

**Request `groove.apply.request.v1`:**

```json
{
  "schema_version": "groove.apply.request.v1",
  "artifact_id": "ga1_<sha256>",
  "track_index": 3,
  "clip_index": 2,
  "source_track_index": 0,
  "source_channel": 9,
  "kit_mapping_profile": "gm-drums-v1",
  "mode": "preview|commit",
  "expected_empty_slot": true
}
```

`track_index` e `clip_index` são obrigatórios e session-local, exatamente como
outros locators do servidor. `commit` requer `expected_empty_slot=true`; o
wrapper pode fazer um preflight local para produzir feedback rápido, mas a
verificação autoritativa é a precondition `slot_empty` validada pela ponte no
mesmo dispatcher/event-loop que abriria o undo. Assim, uma mudança do slot entre
o preflight e o dispatch ainda produz `rejected` sem undo e sem mutação.
`preview` resolve artifact, limites e mapping e devolve `ApplyReceiptV1` sem
chamar Live; nesse modo, `expected_empty_slot` continua sendo uma declaração,
não uma leitura do slot.

Em `commit`, o wrapper valida o artifact, aplica a seleção de track/canal e
materializa internamente no máximo 2.048 `NoteSpec`. O bridge call é um único
`run_batch` contendo `preconditions:[{"type":"slot_empty","version":"v1",
"params":{"track_index":track_index,"clip_index":clip_index}}]`,
`create_clip` e `add_notes_to_clip`, com uma unidade de undo. Falha de transporte
após envio não é repetida. A ferramenta nunca faz readback para transformar uma
falha ambígua em sucesso. O receipt usa `committed`, `partial` ou `unknown` de
acordo com `ApplyReceiptV1`; não há booleano `applied` que esconda prefixo
persistido ou estado ambíguo.

### 10.6 Preconditions backward-compatible da ponte

O contrato existente de `run_batch` ganha somente um campo opcional:

```json
{
  "commands": [{"type": "create_clip", "params": {"track_index": 3, "clip_index": 2}}],
  "preconditions": [
    {"type": "slot_empty", "version": "v1", "params": {"track_index": 3, "clip_index": 2}}
  ]
}
```

`preconditions` ausente é exatamente `[]`; batches antigos continuam com o
mesmo comportamento, inclusive em uma ponte antiga. A lista tem no máximo 16
itens, não admite duplicatas, `extra` fields ou tipos além de
`slot_empty/v1`. Esse tipo exige inteiros não negativos `track_index` e
`clip_index`, ambos bounded pelos limites da sessão. Para `groove_apply` em
`commit`, exatamente uma precondition `slot_empty` correspondente ao alvo é
obrigatória; o wrapper não envia um batch de apply sem ela.

O `Client` atual mantém `_socket`, `_connected`, `_recv_buffer`, `_lock` e
reconexão para falhas de leitura. A extensão de estado necessária é um
`connection_epoch` inteiro, monotônico e somente leitura: começa em `0`, é
incrementado sob o mesmo `_lock` depois de cada `socket.connect` bem-sucedido e
em toda transição que descarta um socket existente (`close`, timeout, erro de
leitura ou reconexão). `close` é idempotente e não incrementa quando já não há
socket nem estado conectado. Uma conexão que falha antes de conectar não cria
epoch novo; o descarte de uma conexão anterior, se houver, já o criou. O valor
fica exposto junto de um snapshot somente leitura
`{host, port, connected, connection_epoch}`; o socket e o buffer nunca são
expostos. Toda transição de lifecycle usa o mesmo domínio de lock (com helper
interno locked quando o chamador já possui `_lock`). O contador é do transporte
TCP que executa `run_batch`, não do WebSocket.

O cache de capability usa a chave completa `(host, port, connection_epoch)`,
além do TTL de 5 segundos. A propriedade e o snapshot são thread-safe; a
inserção de um status só é aceita se o epoch observado no fim da chamada ainda
for o mesmo do snapshot. Um epoch diferente invalida a entrada imediatamente,
sem esperar TTL, inclusive quando duas chamadas concorrentes compartilham o
mesmo endpoint.

Para fechar a corrida entre handshake e pre-send, o `Client` expõe a operação
atômica:

```text
call_at_epoch(expected_epoch: int, action: str, params: Mapping | None = None,
              *, timeout: float | None = None) -> AtEpochCallResultV1[Any]
```

Ela adquire exatamente `_lock`, não chama `call` internamente e mantém esse
lock durante serialização, `sendall`, leitura do frame e decode da resposta.
Antes de serializar ou enviar um byte, verifica sob o lock
`_connected is true`, `_socket is not None` e
`connection_epoch == expected_epoch`. Desconexão ou divergência levanta o erro
tipado `BridgeEpochMismatchError` (`reason=disconnected|epoch_mismatch`), com
`bytes_sent=0`; não há auto-reconnect, retry ou dispatch. Assim, uma chamada
concorrente não pode trocar o socket entre a validação e o `sendall`.

Quando `sendall`, leitura e decode terminam sob o mesmo lock, o retorno é um
`AtEpochCallResultV1` tipado com exatamente `value` (o valor/receipt decodificado),
`receipt` (`ApplyReceiptV1 | null` quando a ação é apply),
`epoch_used` (capturado nesse lock) e `transport_state="received"`. Um erro de
negócio retornado pela ponte, como `PRECONDITION_FAILED`, também é uma resposta
recebida: seu `value`/`receipt` preserva `rejected` e `epoch_used=E`; não vira
`unknown`. Depois que esse objeto sai do lock, close/reconnect concorrente não
pode reclassificar o resultado confirmado.

Falha de validação/serialização ou falha explicitamente anterior à invocação de
`sendall` levanta `BridgePreSendError` com `bytes_sent=0`, sem mutação. Se
`sendall` falhar depois de poder ter entregue bytes, ou se a leitura/decode
falhar depois do envio, `call_at_epoch` fecha o socket sob o lock, incrementa o
epoch e levanta `BridgeTransportAmbiguousError` com
`outcome=unknown`, `transmission=possible` e `bytes_sent=unknown`; nunca
reconecta nem reenvia. Um teste de transporte que prove falha de `sendall` antes
de qualquer byte pode registrar `transmission=not_sent`, mas o caminho real não
assume isso quando o sistema operacional não prova zero bytes. O receipt mapeia
qualquer outcome após possível transmissão para `unknown`, sem prometer
atomicidade ou fazer retry; somente os erros pre-send podem reiniciar o
handshake sem dispatch.

O fluxo usa o envelope de `bridge_status` descrito aqui; a verificação exige
validar estrutura e valores exatos, não apenas testar a presença de uma chave.
A capability de ponte é negociada antes do envio por `bridge_status`. O formato
atual observado em `diagnostics.bridge_status` mantém campos top-level legados
como `status`, `bridge_available`, `live`, `error`, `hint`, `endpoint`,
`runtime`, `server_version`, `tool_count`, `features`, `capability_counts` e
`capability_gaps`; nenhum deles é renomeado, removido ou reinterpretado. A
extensão adiciona somente o campo top-level opcional `bridge_contract` ao
envelope normalizado. O campo tem tipo `BridgeContractV1 | null` e, quando
presente como objeto, é exatamente:

```json
{
  "schema_version": "bridge.contract.v1",
  "owner": "AbletonMCPServer_RemoteScript",
  "protocol_version": "bridge.v1",
  "capabilities": {"run_batch_preconditions": "v1"}
}
```

O owner do contrato é o Remote Script, não o caller MCP nem o adapter local.
Como fonte, o Remote Script acrescenta o mesmo objeto como campo opcional
`bridge_contract` no resultado de `get_session_info`; o adapter local apenas o
valida e copia para `bridge_status.bridge_contract`, sem alterar os campos
legados dentro de `live`. Ausência do campo, `null`, tipo errado, owner/schema/
protocol desconhecido, capability ausente ou valor diferente de `"v1"` são
todos estados sem capability. Chaves de capability desconhecidas não concedem
permissão e não substituem a chave exata `run_batch_preconditions`.

O estado é obtido somente por uma chamada read-only a `get_bridge_status` (que
usa o `get_session_info` existente); nunca se faz um `run_batch` de sondagem.
O servidor mantém cache em memória pela chave `(host, port, connection_epoch)`
do TCP, com `fetched_at` monotônico e TTL de 5 segundos. Um valor dentro do TTL
é `fresh`;
depois dele é `stale` e pode aparecer em diagnóstico, mas nunca autoriza
`groove_apply`. Status com `bridge_available=false`, erro de transporte,
reconexão, epoch diferente, endpoint diferente, resposta malformada,
owner/schema/protocol incompatível ou capability ausente invalida imediatamente
a entrada. Em cache ausente ou stale, o servidor busca um status novo antes do
preflight; falha da busca, estado stale sem refresh bem-sucedido ou qualquer
validação negativa
retorna `GROOVE_PRECONDITION_UNSUPPORTED`. Não existe fallback para usar cache
stale, remover `preconditions` ou tentar a mutação sem proteção.

O fluxo de negotiation é: (1) validar localmente o request e exigir
`expected_empty_slot=true`; (2) capturar `epoch_before_status`, obter status
fresh e capturar `epoch_status`; se mudarem, descartar o resultado e repetir o
handshake uma vez no epoch atual; nova mudança ou falha é closed com
`GROOVE_PRECONDITION_UNSUPPORTED`; (3) validar
`bridge_status.bridge_contract` pela estrutura e pelos valores exatos e aceitar
somente o par
`protocol_version="bridge.v1"` e `capabilities.run_batch_preconditions="v1"`;
(4) fixar `E=epoch_status`, fazer o preflight local e capturar
`epoch_before_batch`; se for diferente de `E`, reiniciar o handshake/preflight e
falhar closed se não houver epoch estável; (5) enviar o único batch somente por
`call_at_epoch(E, "run_batch", batch)`; seu retorno `AtEpochCallResultV1` tem
`epoch_used=E` sob o lock e fixa o valor/receipt recebido; (6) se a ponte
retornar `PRECONDITION_UNSUPPORTED`, invalidar o cache e
produzir `GROOVE_PRECONDITION_UNSUPPORTED`/`rejected`, sem retry e sem reenviar
um batch desprotegido. Timeout depois do envio continua sendo `unknown`, não é
tratado como ausência de capability. Não há segunda leitura externa do epoch
nem reclassificação por uma mudança depois que o resultado foi devolvido.

`BridgeEpochMismatchError` ou `BridgePreSendError` nessa etapa significa que
zero bytes foram enviados: o servidor não cria receipt `unknown`, não chama o
dispatcher e reinicia o handshake uma vez ou retorna
`GROOVE_PRECONDITION_UNSUPPORTED`/`rejected` closed. Somente
`BridgeTransportAmbiguousError` depois de `call_at_epoch` ter começado o envio
produz `unknown`; close/reconnect posterior ao retorno de
`AtEpochCallResultV1` não altera `committed` nem `rejected`.

O admission guard de uma ponte nova `bridge.v1` é obrigatório e fica no
dispatcher de `run_batch`, antes de `_begin_undo`/`begin_undo_step`: se o campo
`preconditions` estiver presente e a ponte não anunciar exatamente o contrato
acima, retorna `PRECONDITION_UNSUPPORTED`, não executa comando, não abre undo e
nunca ignora o campo extra. Batches sem o campo preservam o comportamento
legado. Uma nova versão ou schema exige novo identificador e nova validação.

O limite de compatibilidade é explícito: somente o servidor mediado por este
contrato garante que `groove_apply` não abre undo nem muta Live quando a
capability falta. Uma cópia física antiga do Remote Script, sem
`bridge_contract`, é incompatível com `groove_apply`; o servidor nunca envia a
ela um batch com `preconditions` e retorna `GROOVE_PRECONDITION_UNSUPPORTED`.
Um cliente direto que envie `preconditions` a essa cópia antiga está fora do
contrato, pode obter rejeição parcial ou até abrir undo vazio se o parser antigo
ignorar o campo, e nunca deve ser descrito como seguro. A garantia de rejeição
antes de `begin_undo_step` para cliente direto existe somente em bridge nova com
o admission guard `bridge.v1`.

No dispatcher da ponte, depois do admission guard, a sequência normativa é: (1)
decodificar e validar todos os itens de `preconditions`; (2) avaliar cada item
contra o estado Live atual, sem executar comando e sem short-circuitar a fase de
validação; (3) se
qualquer um falhar, retornar erro estruturado
`PRECONDITION_FAILED` com `precondition_index`, `type`, `expected` e
`observed` do primeiro índice falho em ordem de entrada,
`bridge_stage=precondition`, sem chamar `begin_undo_step`, sem
executar comando e sem mutar Live; (4) somente se todos passarem, chamar
`begin_undo_step` e executar os comandos na ordem existente. A avaliação e o
início do undo acontecem no mesmo dispatcher/event-loop, sem ponto de
interleaving de outro evento Live; `create_clip` ainda mantém sua checagem de
slot ocupado como defesa secundária. `PRECONDITION_FAILED` é erro de alvo
bounded, não exceção de transporte, e nunca é convertido em `partial` ou
`unknown`.

Os testes normativos cobrem: (a) status de bridge antigo sem
`bridge_contract`; (b) batch legado sem `preconditions` mantendo o comportamento
anterior; (c) bridge capaz -> disconnect -> bridge incapaz no mesmo `(host,port)`
antes de 5s, falha de leitura com retry que incrementa epoch e invalida cache,
além de chamadas concorrentes que disputam o handshake; o fixture força essa
troca exatamente entre handshake e `call_at_epoch` e confirma zero bytes
enviados, zero dispatch e zero `begin_undo_step`;
(d) `call_at_epoch` com `epoch_mismatch` e socket desconectado, ambos com zero
bytes; falha de `sendall` comprovadamente antes de bytes e falha depois de
transmissão possível, distinguindo `BridgePreSendError` de
`BridgeTransportAmbiguousError`/`unknown`, sem reconectar ou reenviar; (e)
contrato ausente,
malformado, owner/schema/protocol incompatível ou capability sem a versão
exata; (f) cliente direto em bridge nova sem capability, rejeitado antes de
`begin_undo_step`, e cliente direto em cópia antiga explicitamente marcado fora
do contrato; (g) contrato suportado com precondition válida, um undo e create
bem-sucedidos; (h) slot ocupado sem undo/mutação; (i) todas as preconditions
avaliadas antes do undo; e (j) TOCTOU em que o preflight do servidor observa slot
vazio, o fixture ocupa o slot antes do dispatch, e a ponte retorna
`PRECONDITION_FAILED`/`rejected` com contagens zero. Também há fixtures
`create-success/add-fail` e transporte ambíguo para provar que a precondition
não promete rollback nem altera os estados `partial`/`unknown` já definidos;
(k) resposta `committed` confirmada e resposta `rejected` recebida com
`epoch_used=E`, seguidas de `close` concorrente antes de o caller inspecionar o
objeto, permanecem nos estados originais e nunca são reclassificadas como
`unknown`.

O rollout é ordenado: (1) atualizar a fonte autoritativa do Remote Script e
todas as cópias/projeções físicas usadas pelo checkout, wheel e instalação no
Live; (2) executar o capability probe de `bridge_status` e confirmar o objeto
`bridge_contract` completo no epoch atual; (3) atualizar as fixtures de
igualdade exata de `tests/test_acceptance_audit_p0p1.py`, especialmente o
`session == {...}` de `get_session_info`, para incluir o `bridge_contract` exato
na fixture capaz e uma asserção explícita de ausência/null na fixture antiga;
não trocar igualdade por um teste de subconjunto; (4) somente depois habilitar
`groove_apply`. Qualquer cópia que falhe o probe permanece com a ferramenta
desabilitada, mesmo que outros comandos legados ainda funcionem.

## 11. Rotas, Pydantic e FastMCP

Cada request será um modelo Pydantic v2 nomeado, com `schema_version` literal,
limites declarados e validação cruzada. A tabela de catálogo planejada é:

A escolha de wire é **argumentos explícitos de topo**, não um parâmetro
`request` aninhado. Cada wrapper FastMCP expõe `schema_version` como argumento
visível e obrigatório, com enum de um valor; o wrapper monta o modelo Pydantic
correspondente e rejeita `extra` fields. A superfície é:

| Tool | Argumentos de topo obrigatórios/centrais |
|---|---|
| `groove_search` | `schema_version`, `query?`, `facets`, `feature_constraints`, `bpm?`, `meter?`, `seed_bundle_id?`, `required_projection_ids?`, `projection_operator?`, `limit`, `cursor?` |
| `groove_evidence` | `schema_version`, `artifact_id`, `query_hash?`, `include_projections` |
| `groove_generate` | `schema_version`, `source`, `transforms`, `bars`, `seed`, `provider` |
| `groove_compare` | `schema_version`, `artifact_ids`, `metrics`, `normalize` |
| `groove_apply` | `schema_version`, `artifact_id`, `track_index`, `clip_index`, `source_track_index?`, `source_channel?`, `kit_mapping_profile`, `mode`, `expected_empty_slot` |

Os valores permitidos de `schema_version` são respectivamente
`groove.search.request.v1`, `groove.evidence.request.v1`,
`groove.generate.request.v1`, `groove.compare.request.v1` e
`groove.apply.request.v1`. O JSON Schema publicado por FastMCP deve mostrar
`schema_version` em `properties`, o literal em `enum`, `additionalProperties:
false` e os campos obrigatórios em `required`; não é suficiente manter a versão
apenas em docstring ou no modelo interno. Um teste de contrato chama
`await mcp.list_tools()`, localiza os cinco nomes e compara cada `inputSchema`
com `model_json_schema()` do modelo Pydantic, incluindo enum, required,
additionalProperties, bounds e unions. Outro teste envia uma versão errada e um
campo extra e comprova rejeição antes de qualquer I/O.

Cada resposta também tem um `schema_version` de topo (`groove.*.response.v1`)
no `structured_content` e no único texto JSON que o wrapper emitir; o teste de
wire valida que o response schema e o request schema não perdem essa versão ao
passar pelo FastMCP.

| Tool | domínio | rota | risco | aceitação |
|---|---|---|---|---|
| `groove_search` | `groove` | `LOCAL` | `READ` | `OFFLINE` |
| `groove_evidence` | `groove` | `LOCAL` | `READ` | `OFFLINE` |
| `groove_generate` | `groove` | `LOCAL` | `LOCAL_WRITE` | `OFFLINE` |
| `groove_compare` | `groove` | `LOCAL` | `READ` | `OFFLINE` |
| `groove_apply` | `groove` | `COMPOSED` | `REVERSIBLE` | `GUARDED` |

`groove_generate` grava somente em um store de artefatos local, content-addressed
e bounded; não é mutação Live. `groove_apply` é a única ferramenta nova que
entra na ponte. Os wrappers FastMCP devem usar o mesmo padrão de
`_explicit_json_result` e erros estruturados já usado em `server.py`.

Erros de validação continuam erros Pydantic/MCP antes de qualquer I/O. Erros de
índice usam códigos `GROOVE_INDEX_UNAVAILABLE`, `GROOVE_SCHEMA_UNSUPPORTED`,
`GROOVE_ARTIFACT_NOT_FOUND`, `GROOVE_LIMIT_EXCEEDED`, `GROOVE_BLOB_REJECTED`,
`GROOVE_PROVENANCE_INVALID`, `GROOVE_RIGHTS_BLOCKED` e
`GROOVE_RESPONSE_BUDGET_EXCEEDED`. Cursor malformado ou incompatível usa
`GROOVE_CURSOR_INVALID` ou `GROOVE_CURSOR_QUERY_MISMATCH`. Erros do alvo usam
`GROOVE_TARGET_INVALID`, `GROOVE_TARGET_OCCUPIED`,
`GROOVE_APPLY_SCOPE_REQUIRED`, `GROOVE_APPLY_CHANNEL_UNSUPPORTED`,
`GROOVE_APPLY_TOO_MANY_NOTES`, `GROOVE_PRECONDITION_UNSUPPORTED`,
`GROOVE_PRECONDITION_FAILED` e `GROOVE_APPLY_FAILED`. O erro estruturado
`PRECONDITION_FAILED` da ponte é normalizado para
`GROOVE_PRECONDITION_FAILED`, preservando `bridge_stage=precondition`;
`PRECONDITION_UNSUPPORTED` é normalizado para
`GROOVE_PRECONDITION_UNSUPPORTED`.
`GROOVE_PROVIDER_UNAVAILABLE` não é erro terminal quando o fallback determinista
produz um artefato válido; ele aparece como warning e `fallback.reason`.

A atualização de catálogo/modelos/servidor deve preservar a invariável
`set(TOOL_REQUEST_MODELS) == {spec.name for spec in TOOL_CATALOG}` e ser feita
junto dos testes de registro, contagem e FastMCP. Nenhum contrato vendorizado ou
Remote Script é alterado por `groove_search`, `groove_evidence`,
`groove_generate` ou `groove_compare`.

## 12. Provider neural separado

### 12.1 Interface e subprocesso

O núcleo define apenas um protocolo de provider:

```text
generate(condition_card, parent_artifact_ids, seed, limits)
    -> ProviderArtifactCandidate | ProviderFailure
```

`condition_card` contém features/facets/HVO bounded e não dá ao provider acesso
ao SQL, caminho do corpus ou BLOB bruto. A saída candidata é tratada como
não confiável: passa por schema, parser, limites, hash, projections e
proveniência antes de entrar no store. Kit mapping não é enviado ao provider;
permanece tardio no `groove_apply`.

O adapter neural é um subprocesso real, criado pelo host somente quando
`provider="neural"` e a instalação opt-in estiver disponível. A seleção usa um
registry local allowlisted por `provider_id`, `executable_digest`, versão e
argv fixa; o request nunca fornece executable, argv, shell ou diretório.
O processo é iniciado sem shell, com cwd em diretório temporário exclusivo e
permissões do usuário do servidor. O ambiente é uma allowlist (`PATH` mínimo,
`TEMP`, `TMP`, `PYTHONNOUSERSITE=1` e locale `C`); tokens, proxies, chaves e
variáveis de cloud são removidos. O diretório temporário é apagado após o
processo.

IPC é stdin/stdout com frames JSON UTF-8 length-prefixed. Métodos permitidos
são exatamente `hello`, `generate` e `shutdown`; qualquer método, campo
desconhecido ou frame acima de 256 KiB é violação de protocolo. stderr é
capturado até 16 KiB, sanitizado para remover paths e segredos, e nunca é
devolvido ao MCP. O processo não recebe socket, URL ou acesso a SQL; não depende
de rede ou GPU. Se o provider declarar GPU obrigatória ou o host não puder
aplicar a política offline, o host recusa o provider e usa o fallback
determinístico.

Limites fixos do subprocesso: startup 2 s, `generate` 5 s, shutdown 1 s,
memória 512 MiB, CPU 2 s por geração, resposta JSON 256 KiB, profundidade JSON
8 e 2.048 eventos candidatos. Timeout, limite ou protocolo inválido mata o
processo e seus descendentes sem retry. Em Windows isso exige Job Object; em
outros hosts exige process group equivalente. Se a ferramenta de isolamento não
estiver disponível, o provider fica `not_installed`/`launch_denied` e o fallback
determinístico segue normalmente.

Falhas internas são reduzidas aos enums estáveis
`not_installed`, `launch_denied`, `offline_policy`, `protocol_violation`,
`timeout`, `exit_nonzero`, `output_too_large`, `output_invalid`,
`resource_limit` e `internal`. Mensagens externas carregam somente enum,
provider_id e um digest curto do diagnóstico; stdout/stderr, caminhos e
comandos não atravessam a fronteira MCP.

### 12.2 Fallback e reprodutibilidade

O fluxo é:

1. validar request, direitos e parent artifact;
2. iniciar o subprocesso allowlisted com timeout bounded;
3. validar e canonicalizar a saída;
4. se falhar, registrar `provider_failure_code` enum e executar o generator
   determinístico com o mesmo `seed`, limites e parent;
5. retornar `provider_resolved="deterministic"`, `fallback=true` e a razão.

Se o determinístico também falhar, a chamada falha com erro estruturado. Falha
neural jamais devolve um payload parcial nem marca provider neural como sucesso.
Uma execução neural só é reprodutível se o card incluir digest do modelo,
runtime, configuração de sampling, provider version, seed e parent ids; ausência
de qualquer identidade torna a chamada inválida para produção e admissível
somente no laboratório.

### 12.3 Laboratório e gates

O laboratório é um ambiente separado do runtime e não habilita provider por
configuração implícita. Antes de qualquer promoção, o candidato precisa passar
os gates versionados:

- **contrato:** schema, limites MIDI, parser, hash, mapping e ausência de
  eventos inválidos;
- **fallback:** provider ausente, timeout, erro de processo, saída inválida e
  incompatibilidade reproduzem um resultado determinístico válido;
- **reprodutibilidade:** mesma identidade de modelo/configuração/seed gera o
  mesmo digest quando o provider declara determinismo;
- **qualidade:** métricas HVO/features/gramática atingem limiares publicados no
  relatório do experimento;
- **privacidade/licença:** nenhuma entrada de corpus bloqueada é exposta,
  nenhum caminho local aparece e o lineage é completo;
- **custo/latência:** limites de CPU, memória, BLOB e timeout são respeitados.

Um gate reprovado mantém o provider fora do runtime. O sistema continua apto a
entregar deterministicamente sem qualquer artefato do laboratório.

## 13. Skill fina

A skill planejada será uma camada de orientação, não um segundo runtime. Ela:

- explica quando usar as cinco ferramentas e como encadear
  `search -> evidence -> generate/compare -> apply`;
- exige exibir `artifact_id`, provenance e fallback antes de sugerir aplicação;
- pede confirmação do alvo e de slot vazio para `groove_apply`;
- limita respostas a cards, receipts e ids;
- trata `artifact_id` como opaco e nunca tenta inferir um caminho;
- instrui o agente a relatar incompatibilidade, licença e mapping unresolved.

A skill não executa SQL, não abre SQLite, não lê BLOB, não varre corpus, não
instala provider, não chama scripts de build e não controla Live por fora das
ferramentas MCP.

## 14. Segurança, falhas e compatibilidade operacional

- Índices abertos pelo host são read-only, immutable e validados contra manifest
  digest antes de qualquer busca.
- Toda consulta é parametrizada; nomes e operações aceitos vêm de uma lista
  fechada do adapter.
- Compressão é bounded por bytes, razão, checksum e codec; payloads não são
  desserializados com pickle ou executados.
- Cards removem caminho, segredo, conteúdo raw e dados além dos limites.
- `artifact_id` inexistente, seed incompatível, projection ausente ou licença
  bloqueada geram erro/card de capability explícito.
- Aplicação respeita os locators session-local atuais, não persiste handles e
  não reusa um índice de slot depois de edição estrutural.
- `run_batch` não é rollback: um prefixo aceito pode persistir dentro de um undo
  agrupado; receipt e documentação devem refletir isso.
- Falha ambígua de mutação nunca é automaticamente repetida.
- O default determinístico não requer Live, rede, provider neural, corpus,
  pacote opcional ou sessão do usuário.

### 14.1 Superfícies de aceitação

A implementação só pode fechar cada fase depois de atualizar todas as
superfícies acopladas, sem varrer o corpus privado:

- **schemas e runtime:** modelos Pydantic, JSON Schema FastMCP, `server.py`,
  `catalog.py`, `PUBLIC_TOOL_FUNCTIONS`, `TOOL_REQUEST_MODELS` e testes de
  registro; a invariável é derivada (`len(TOOL_CATALOG) ==
  len(TOOL_REQUEST_MODELS) == len(PUBLIC_TOOL_FUNCTIONS)`) e os cinco nomes são
  exigidos por conjunto, sem hardcode de uma contagem total futura;
- **fixtures offline:** um conjunto pequeno de SMFs sintéticos versionados para
  round-trip lossless, ids, HVO, features, gramática, direitos, ranking,
  orçamento, PPQ e mapping; nenhum fixture referencia a raiz privada;
- **probes MCP:** `tests/test_groove_schema.py`,
  `test_groove_index.py`, `test_groove_search.py`,
  `test_groove_generation.py`, `test_groove_budget.py`,
  `test_groove_rights.py`, `test_groove_provider.py` e
  `test_groove_apply.py` cobrem os contratos e estados normativos;
- **acceptance runner:** `ableton_mcp_server/acceptance/probes/offline.py` e
  `probes/__init__.py` registram search/evidence/generate/compare e
  `groove_apply` em preview; commit de apply fica em probe guarded com Set
  descartável, slot vazio e confirmação de projeto, usando a mesma proteção
  das mutações existentes;
- **capability/catalog/docs:** `diagnostics.py`,
  `tests/test_capability_matrix.py`, `docs/TOOL_REFERENCE.md`,
  `docs/api_capability_matrix.md`, `docs/ARCHITECTURE.md` e `README.md`
  recebem a origem/catalogação das cinco ferramentas, suas rotas, aceitação,
  limites e ausência de requisito Live para as quatro locais;
- **compatibilidade existente:** testes de `music_brain`, `music_tools`,
  catálogo, modelos, registry, server tools, acceptance offline e packaging
  continuam passando; contagens textuais históricas passam a ser derivadas do
  catálogo ou atualizadas para a presença nominal dos cinco tools, nunca fixadas
  em um número futuro não gerado; `tests/test_acceptance_audit_p0p1.py` atualiza
  a igualdade exata de `get_session_info` para a fixture capaz incluir
  `bridge_contract` e mantém fixture antiga com ausência/null explícita.

O gate de apply exige fixtures específicos para create-success/add-fail,
slot ocupado, mapping unmapped, transporte ambíguo e limite de 2.049 notas.
Esses casos devem verificar `partial`, `rejected` e `unknown`, contagens,
`clip_ref`, recovery e ausência de retry, não apenas um booleano de sucesso.
Em particular, create-success seguido de erro explícito em add produz
`partial`, `bridge_stage=add_notes_to_clip`, `clip_ref.created=true` e
`confirmed=0`; transporte perdido depois do envio produz `unknown`,
`bridge_stage=transport_after_send`, `clip_ref.created=unknown` e
`confirmed=null`. Slot ocupado, rights bloqueado, canal/escopo inválido e 2.049
notas produzem `rejected` antes de abrir undo. Também são obrigatórios os
fixtures de capability `run_batch_preconditions.v1`, batch legado sem
`preconditions`, precondition inválida, validação de todas as preconditions antes
de undo e TOCTOU (preflight vazio, slot ocupado antes do dispatch), verificando
`GROOVE_PRECONDITION_FAILED`, `bridge_stage=precondition`, contagens zero e
zero chamadas a `begin_undo_step`.

## 15. Quatro fases aprovadas e gates

As fases são marcos de entrega, não uma lista de tarefas de implementação.
Nenhuma fase seguinte pode alterar o contrato congelado sem nova decisão.

### Fase 1 — normalização, lossless e índice portátil

**Entregáveis:** `MidiArtifactV1`, canonicalização/hash, build manifest,
proveniência/licença, HVO/features/grammar versionados, schema do índice
read-only, seed bundle portátil e relatório de limites.

**Gate:** dois builds sobre a mesma entrada e configuração produzem o mesmo
manifest digest, `logical_index_digest`, artifact ids, projeções, lineage,
payload/projection digests e cards canônicos; diferenças de bytes físicos do
SQLite não reprovam quando o digest lógico coincide. Nenhum caminho privado
aparece; parser, schema `user_version`, dependências e codec são os fixados
nesta spec; arquivos acima dos limites e BLOBs inválidos são rejeitados; o seed
abre sem o corpus de origem.

### Fase 2 — busca e evidência

**Entregáveis:** adapter SQL parametrizado, ranking multi-eixo, filtros,
cursor, `ArtifactCardV1`, `EvidenceCardV1`, erros bounded e testes de limites.

**Gate:** `groove_search` e `groove_evidence` funcionam sem Live e sem provider;
ranking e desempate são estáveis; filtros AND/OR e artefato inexistente têm
comportamento definido; nenhum response contém notas, BLOB ou path; consultas e
decompressão respeitam limites.

### Fase 3 — geração, MCP, mapping e aplicação

**Entregáveis:** generator determinístico versionado, lineage e
`reproducibility_key`, cinco schemas/tool wrappers, mapping tardio,
`groove_apply` sobre a ponte existente, extensão backward-compatible
`run_batch.preconditions` negociada por capability, skill fina e adaptador de
compatibilidade com `music_*`.

**Gate:** as cinco ferramentas aparecem no FastMCP e no catálogo com modelos
correspondentes e JSON Schemas acessíveis; busca/evidência/geração/comparação
são offline; mesma entrada repete o mesmo artifact id; aplicação preview não
chama Live, todas as cópias/projeções do Remote Script passam o capability probe
no `connection_epoch` atual, commit negocia `run_batch_preconditions.v1`, envia
um único batch por `call_at_epoch(E, "run_batch", batch)` com `slot_empty` e não
sobrescreve slot; `committed`,
`partial`, `rejected` e `unknown` são testados com contagens/recovery; falhas e
fallback de mapping são explícitos; testes legados de `music_brain` e
`music_tools` permanecem verdes.

### Fase 4 — provider neural e laboratório

**Entregáveis:** protocolo separado, adapter opt-in, fixtures de falha,
identidade de modelo/configuração, relatório de experimento e gates de promoção.

**Gate:** remover o subprocesso não quebra instalação nem modo determinístico;
launch denied, offline violation, timeout, kill, IPC inválido, saída inválida e
ausência neural retornam artefato determinístico com warning e enum sanitizado;
nenhum gate de contrato, segurança, privacidade, licença, reprodutibilidade ou
custo fica sem evidência; promoção permanece desligada se qualquer gate falhar.

## 16. Verificação da especificação

Esta especificação foi revisada contra os requisitos do gate e contra os pontos
de integração atuais:

- runtime offline determinístico e seed portátil estão definidos sem dependência
  do caminho do corpus;
- representação lossless e as três projeções têm schemas e vínculo com eventos;
- taxonomia é explicitamente multi-eixo;
- pitch mapping preserva original e declara método/fallback/unmapped;
- as cinco ferramentas têm requests, responses, limites e efeitos definidos;
- cards e `artifact_id` substituem dumps de notas na superfície nova;
- compatibilidade dos três `music_*` legados está explicitamente delimitada;
- SQL parametrizado, read-only, limites de BLOB/descompressão e skill sem SQL/BLOB
  estão normativos;
- neural é separado, opt-in, com fallback determinístico e gates de laboratório;
- as quatro fases têm entregáveis e gates sem virar plano de tarefas;
- `artifact_id` usa domínio explícito, preimage sem id e digests obrigatórios;
- orçamento agregado de 524.288 bytes tem truncamento/error determinístico e
  permanece compatível com `limit=50` e compare de até oito ids;
- aplicação atual respeita 2.048 notas, um clip/canal selecionado, canal 9 no
  perfil GM, seleção de escopo,
  conversão PPQ->beats, precondition `slot_empty` no dispatcher e estados
  `partial`/`unknown` sem chunking prometido;
- direitos usam meet conservador no lineage e bloqueiam generate/apply quando
  license/capability não autoriza;
- provider neural é subprocesso offline real com IPC allowlist, ambiente,
  temp, timeout, kill, output e enums sanitizados definidos;
- DDL SQLite, `user_version`, índices, migração, modo `ro+immutable`, manifest e
  digest lógico estão explícitos, assim como parser/serializer stdlib versionados;
- ranker, normalização, operadores, pesos condicionais e cursor estão presos a
  versões/digests;
- `request_hash` tem canonical JSON, domínio, campos e exclusão explícita de
  `cursor`; checksum e comparação de digest são constantes no tempo;
- handshake de bridge usa `bridge_status.bridge_contract` top-level opcional,
  owner/schema/protocol/capability exatos, `connection_epoch`, cache TTL/stale e
  `call_at_epoch`, retorno com `epoch_used` sob lock, falha fechada e receipt
  `unknown` pós-transmissão; close posterior não reclassifica resposta recebida;
  somente bridge novo garante admission guard, cópia antiga e cliente direto
  ficam fora da garantia;
- wire schema escolhe argumentos de topo com `schema_version` acessível e teste
  de JSON Schema; acceptance cobre runtime, probes, fixtures, capability e docs;
- não há dependência implícita de Live, rede, instalação ou banco criado neste
  trabalho.

O arquivo é uma especificação de design somente. Nenhum produto, teste,
dependência, corpus, banco, skill ou configuração foi criado ou modificado por
este documento.
