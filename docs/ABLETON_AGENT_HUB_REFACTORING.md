# Direcionamento de Refatoração — `ableton-agent-hub` → `ableton-mcp-server`

> Documento de **direcionamento estratégico** baseado na comparação entre o repositório remoto
> [`8309/ableton-agent-hub`](https://github.com/8309/ableton-agent-hub) (HEAD
> `7ed73e42a726e5dc4a54759dda0bd09035c1bc3e`, tag `v0.1.0-alpha`) e o repositório local
> `ableton-mcp-server` (HEAD `7e4c8d0`, v0.5.1, 65 ferramentas MCP). **Não é uma especificação
> executável nem uma mudança de código.** É um guia de decisão para priorização de refatorações.
>
> Toda afirmação sobre o repositório remoto foi extraída do README, da estrutura de
> `ableton_agent/` e da listagem de `docs/` observadas em `main`. Toda afirmação sobre o
> repositório local foi extraída de `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`,
> `docs/KNOWN_BUGS.md`, `docs/INSPIRATION.md` e `.agent-context/architecture.md`. Não foram
> inventadas capacidades: quando um detalhe não pôde ser confirmado, ele está marcado como
> "[verificar]".

---

## 1. Contexto verificado

### 1.1 `ableton-mcp-server` (local)

| Item | Valor verificado |
|---|---|
| Versão atual | v0.5.1 (commit `7e4c8d0`) |
| Protocolo MCP | FastMCP sobre stdio |
| Bridges Live | TCP JSONL `127.0.0.1:9888` (Remote Script → Python LOM) + WebSocket JSON-RPC `127.0.0.1:9889` (Extension → Node LOM) |
| Ferramentas públicas | 65 (asserted por `tests/test_server_tools.py`) |
| Comandos roteados remotos | 55 (26 leituras, 29 mutações permitidas, 5 bloqueadas, 3 alvos WS) |
| Validação de plataforma | Live 12.4.5b7, Python 3.11+, Windows (WSL precisa lançar `.exe` Windows via interoperabilidade) |
| Identidade de objetos | path-IDs `track:N/device:M` — **locators session-local**, não handles estáveis (ver `docs/ARCHITECTURE.md` §"Path-Id Scheme") |
| Modelo de mutação | Diferida via geradores + `update_display`; `run_batch` é **agrupamento de undo**, não rollback; mutações nunca são reexecutadas após falha ambígua |
| Pacote de domínio | `ableton_mcp_server.analysis` (LUFS-I, true-peak, single-cycle) é independente de Live |
| Publicação | MIT, agente único, WSL documentado |

### 1.2 `ableton-agent-hub` (remoto, v0.1.0-alpha)

| Item | Valor verificado |
|---|---|
| Tag/Commit | v0.1.0-alpha (`7ed73e42a726e5dc4a54759dda0bd09035c1bc3e`) |
| Natureza | "Unofficial local Max for Live bridge and Python toolkit" (README) |
| Transporte | UDP `7400` (cliente → Hub) / `7401` (Hub → cliente); **sem autenticação, local-only** |
| Surface adapter | Um único dispositivo `Ableton Agent Hub.amxd` colocado em uma trilha MIDI (não um Control Surface MIDI Remote Script) |
| Validação de plataforma | Windows + Live 12.3.5 + Max for Live + Python 3.12.13 (explicitamente declarado); outros SOs e versões **não verificados** |
| Identidade de objetos | "Stable Live object IDs preferred over changing track indices" (README, seção Safety Model) |
| Modelo de segurança | Mutações são **dry-run por padrão**; writes exigem `--commit` explícito; commit relê o estado afetado quando o Live API permite; leituras não modificam o Set intencionalmente; writes não suportadas **falham** em vez de cair em automação de UI |
| Instalador | `ableton-agent.exe install` copia Hub + JS modules com **SHA-256** por arquivo; não deleta outros arquivos; suporta `--destination PATH` |
| Foco da v0.1.0-alpha | Read de Set/track/device/parameter/clip/scene/locator/routing/meter; write de tempo/transporte/mixer/parâmetros do device selecionado/clips/scenes/locators/routing; ajuda em seleção de samples locais; confirma samples do Simpler/Drum Rack quando o Live API expõe o caminho |
| Limites conhecidos | Documento `docs/live_api_limits.md` separa áreas experimentais/bloqueadas |
| Pacotes Python | `ableton_bridge` com clientes focados (módulos `track_management`, `parameter_summary`, `sample_confirm` mencionados no README como exemplos executáveis) |
| Recursos auxiliares | `ableton_agent/dist/`, `ableton_agent/max/`, `ableton_agent/sample_index/`, `ableton_agent/schemas/`, `ableton_agent/sound_catalog/`, `ableton_agent/styles/`, `ableton_agent/build_hub_device.py` |
| Publicação | MIT, alpha público, "test on a copy" |

### 1.3 Diferenças estruturais relevantes

1. **Surface adapter**: o hub remoto é **um Max for Live device** carregado em uma trilha MIDI. O servidor local usa **MIDI Remote Script** + **Ableton Extension (Node.js)**. Migrar entre os dois modelos não é trivial; é uma decisão arquitetural, não uma melhoria incremental.
2. **Transporte**: UDP bidirecional sem framing contra TCP+WS confirmados e testados com loopback-only. O servidor local tem framing (newline-delimited JSON ≤1 MiB), timeouts determinísticos (`contracts.request_timeout_seconds`) e retry policy explícita (lê novamente; nunca reexecuta mutação).
3. **Identidade de objeto**: o hub remoto prioriza "stable Live object IDs" — o servidor local explicitamente afirma que path-IDs **são locators e não handles estáveis**. Esses são pontos de vista diferentes; o local expõe a fragilidade como parte do contrato.
4. **Granularidade de mutação**: o servidor local opera em 65 ferramentas com allowlist tripla (`READ_COMMANDS`/`ALLOWED_MUTATIONS`/`READ_ONLY_COMMANDS`). O hub remoto é mais conservador no write (tempo + estrutura, não notas MIDI nem envelopes), mas torna o dry-run default universal.
5. **Foco de domínio**: o servidor local investe pesadamente em Session clips, MIDI notes, batch undo, fade, lifecycle e análise offline de mix. O hub remoto investe em seleção de samples, índice de samples e estilo/catálogo.

---

## 2. Melhorias recomendadas (específicas, pequenas, testáveis)

> Critério: itens onde a evidência observada no hub remoto é **diretamente portável** para o
> servidor local sem reescrever o modelo de transporte, sem mudar a natureza do surface adapter
> (MIDI Remote Script + Extension) e sem afetar contratos existentes.

### R1. Identidade de mutação estável em logs

**Origem**: hub remoto, Safety Model ("Stable Live object IDs preferred over changing track indices"; "A commit reads affected state back when the Live API permits it").

**Problema no local**: `docs/ARCHITECTURE.md` §"Path-Id Scheme" já afirma que `track:2/device:1` são locators. Mas o envelope de erro hoje não inclui metadados que permitam correlacionar o erro ao **objeto Live real** afetado, só ao path-id da chamada.

**Mudança proposta**:
- Quando o LOM expõe um handle/identificador estável para um objeto (e.g., nome de track, índice de dispositivo, ID de sessão de cue, ID de clip), incluir no envelope de resposta — em **modo opt-in via flag de tool** ou em respostas de mutação — uma seção `resolved` com `{track_name, device_name, index, kind}` ao lado do path-id.
- Atualizar `client.py` para que o campo seja preenchido por reflexão quando o handler remoto retornar o objeto.
- Atualizar `docs/TOOL_REFERENCE.md` marcando quais tools podem devolver `resolved`.

**Aceitação**:
- Pelo menos 3 ferramentas de mutação (`set_parameter_value`, `create_clip`, `set_tempo`) emitem `resolved` em testes novos.
- Erros `STALE_REFERENCE` continuam diferenciados de erros de "resolved mismatch".
- Nenhuma mudança em `contracts.py` que afete a fronteira do Remote Script sem regenerar `_contracts.py`.

### R2. Dry-run explícito por ferramenta de mutação

**Origem**: hub remoto, Safety Model ("Mutating commands preview by default. `--commit` is required for a supported write.").

**Problema no local**: o servidor local **não tem** um modo preview. Toda mutação validada pelo allowlist executa imediatamente. `run_batch` agrupa em um único undo step mas não pré-visualiza.

**Mudança proposta (mínima)**:
- Adicionar uma flag opcional `dry_run: bool = False` no Pydantic de 3–5 ferramentas de mutação que tocam o Set de forma cara (e.g., `load_device_to_track`, `create_audio_track`, `create_clip`, `set_loop_length`, `live_fade`).
- Quando `dry_run=True`, o handler **valida a entrada, resolve o alvo e devolve o que mudaria**, mas **não aplica** a mutação e **não cria undo step**.
- Não é default; não é retroativo. Tools existentes permanecem write-on-call.
- Adicionar à `AGENTS.md` linha sobre a nova convenção.

**Aceitação**:
- A chamada `dry_run=True` retorna o mesmo shape de resposta da versão real, exceto pelo campo `committed: false`.
- A chamada `dry_run=False` (default) tem comportamento idêntico ao anterior (teste de regressão).
- Não introduz nova flag nos comandos roteados do Remote Script (mantém `ALLOWED_MUTATIONS` em paz).

### R3. README/installer com verificação SHA-256

**Origem**: hub remoto (README §"Install From A Checkout": "verifies every file with SHA-256").

**Problema no local**: `scripts/setup_windows.ps1` no local já faz `md5sum` no Remote Script copiado (ver `docs/reports/2026-07-09-install-and-wsl-incompat.md` linha 4 do checklist). SHA-256 é mais robusto e o hash deve ser exibido para auditoria.

**Mudança proposta**:
- Em `scripts/setup_windows.ps1`, substituir MD5 por SHA-256 (Python `hashlib` ou `Get-FileHash -Algorithm SHA256`).
- Imprimir hash e caminho de destino para que o usuário cole na seção "Verify Install" do README.
- Adicionar seção curta "Verify Install" em `README.md` mostrando como rodar a verificação depois da instalação.

**Aceitação**:
- `setup_windows.ps1` termina imprimindo pelo menos um bloco com algoritmo, hash e caminho.
- Teste novo em `tests/` exercita o cálculo sobre o Remote Script atualmente versionado e compara com hash fixo (regenerado se o Remote Script mudar).

### R4. Capability matrix local, espelhada de `docs/api_capability_matrix.md`

**Origem**: hub remoto — README declara a capability matrix como "row-by-row source of truth"; o doc `live_api_limits.md` separa áreas experimentais/bloqueadas.

**Problema no local**: hoje `docs/TOOL_REFERENCE.md` lista as 65 ferramentas e `docs/KNOWN_BUGS.md` documenta quirks. Mas **não há um único arquivo que diga "isto é o que o servidor pode fazer, isto não pode, isto é experimental"** sob a perspectiva de uma matriz.

**Mudança proposta**:
- Criar `docs/api_capability_matrix.md` com uma tabela por categoria (tempo, transport, mixer, devices, clips, scenes, locators, samples, MIDI notes, automation, batch, lifecycle, analysis, diagnostics). Colunas sugeridas: `tool`, `read/write`, `requires`, `requires_extension`, `stability`, `live_version_validated`.
- Alimentar automaticamente via script que percorre `PUBLIC_TOOL_NAMES` em `server.py` + `READ_COMMANDS`/`ALLOWED_MUTATIONS`/`READ_ONLY_COMMANDS` em `contracts.py` + `WEBSOCKET_TARGET_COMMANDS`.
- Marcar `lifecycle_status` como read-only (já passa pelo allowlist por design).
- Marcar as 4 ferramentas `ableton_mcp_server.analysis` como "no Live required".

**Aceitação**:
- Script gera o arquivo de forma determinística; diff pequeno quando só se muda o allowlist.
- Doc inclui contagem cruzada: 65 ferramentas públicas, 55 comandos roteados, 3 alvos WS — igual ao que `AGENTS.md` documenta.
- CI roda o script e falha se a contagem não bater.

### R5. Limites do Live API centralizados

**Origem**: hub remoto (`docs/live_api_limits.md`).

**Problema no local**: `docs/KNOWN_BUGS.md` lista mitigações por categoria (A–G+). É o documento certo, mas falta um sumário executivo que diga "estas áreas não tente agora".

**Mudança proposta**:
- Adicionar seção no topo de `KNOWN_BUGS.md` "Don't try these yet" com bullets curtos (Arrangement tempo automation, propriedades read-only que parecem writable, custom beat-time wrappers, track index mudando após structural edits).
- Apontar para `live_api_limits.md`-style counterpart no local — pode ser uma seção interna do próprio `KNOWN_BUGS.md` ou um doc novo `docs/live_api_limits.md` se ficar grande.
- Cross-link de `README.md` para esse sumário na seção de segurança.

**Aceitação**:
- README tem link âncora para o sumário.
- Sumário tem ≤ 1 tela e cada bullet cita o quirk original.

### R6. Comando `dry-run install` para o setup Windows

**Origem**: hub remoto (`ableton-agent.exe install --dry-run`).

**Problema no local**: `scripts/setup_windows.ps1` é executado direto. Não há como "ver o que ele faria sem fazer".

**Mudança proposta**:
- Adicionar parâmetro `-DryRun` ao script.
- Quando presente, listar arquivos que seriam copiados com hash atual vs. destino, sem criar `.venv-win`, sem instalar deps, sem escrever em `User Library/Remote Scripts/`.

**Aceitação**:
- `-DryRun` retorna 0 e imprime plano.
- Sem `-DryRun`, comportamento idêntico (smoke test no fluxo real).

---

## 3. Ideias a avaliar (não óbvias, precisam de design antes)

> Itens onde o hub remoto traz algo interessante mas a移植ação precisa de mais
> investigação. Não implementar antes de abrir uma spec/design doc.

### E1. Stable Live Object IDs

O hub remoto prioriza "stable Live object IDs" sobre índices. O servidor local explicitamente **não** oferece isso (path-IDs são session-local). Avaliar:

- O que o Live API realmente expõe de estável? `Track.name`, `Device.name`, `Clip.name`, `Scene.name` não são únicos por si. Em tese, hashes sobre (track_index, device_index, name) só são estáveis dentro de uma sessão.
- Se a ideia é só "nome em vez de índice", o servidor local já tem `live_find_track(query)` que devolve path-id fresco. Estender para `find_device` e `find_clip` é trabalho pequeno.
- **Recomendação**: começar por `find_device`/`find_clip` como ferramenta read-only em vez de mudar o modelo de path-id.

### E2. UDP como transporte alternativo

O hub remoto usa UDP 7400/7401. O servidor local usa TCP 9888 + WS 9889. Avaliar:

- **Risco de segurança**: UDP sem autenticação em porta aberta é vetor de amplificação em LAN. O servidor local foi desenhado para loopback-only e tem guard explícito em `client.py` (`Ableton bridge host must be loopback 127.0.0.1`). UDP herda esse problema.
- **Não copiar** sem primeiro responder: por que TCP/WS não servem? Se a razão for latência, medir primeiro. Se for conveniência, não vale o risco.
- **Recomendação**: rejeitar — não há evidência de que UDP traga ganho mensurável para o workload atual.

### E3. Max for Live como surface adapter

O hub remoto é um M4L device em uma trilha MIDI. O servidor local usa MIDI Remote Script + Extension (Node). Avaliar:

- Prós do M4L: módulos `jsui` para UI rica, acesso ao `live.api` em Node, dispensa o ciclo Control Surface.
- Contras do M4L: precisa estar em uma trilha da Set, não roda em background, e o `live.api` no M4L **não** é o mesmo objeto Python do MIDI Remote Script — algumas APIs (e.g., `Application.Song`, `Clip.MidiNoteSpecification` completo) só estão no MIDI LOM.
- **Recomendação**: **não migrar**. A combinação MIDI Remote Script + Extension do servidor local cobre tudo o que o hub remoto cobre e ainda permite MIDI notes, batch undo, e lifecycle. M4L viria com perdas reais.

### E4. Hub como produto único vs. 65 ferramentas granulares

O hub remoto tem um CLI unificado `ableton-agent` e clientes focados como submódulos Python (`ableton_bridge.track_management`, `parameter_summary`, `sample_confirm`). O servidor local tem 65 ferramentas MCP, todas no mesmo servidor.

- **Considerar** expor clientes focados **fora** do MCP (como o hub remoto faz). Útil para usuários que querem rodar um script Python sem o ciclo MCP. Não é prioridade porque o MCP já cobre o caso de uso.
- **Recomendação**: adiar. Primeiro, confirmar se há demanda real.

### E5. Sample index / sound catalog

O hub remoto traz `sample_index/`, `sound_catalog/`, `styles/`. O servidor local não tem nada parecido (busca de samples está fora de escopo por enquanto).

- **Avaliar** se faz sentido ter um `search_browser` mais profundo (hoje `search_browser` existe, mas é TCP read de `application.browser`, com bounds). Possivelmente estender para retornar metadados de samples?
- **Recomendação**: spec separada. Não misturar com refatoração de segurança/mutação.

### E6. Capability discovery dinâmico no `doctor`

O hub remoto tem `ableton-agent.exe ping` como checagem de conexão. O servidor local tem `doctor --json` que **deve** completar um round-trip real de `get_session_info` (ver `.agent-context/risks.md`).

- **Considerar** adicionar um modo `--dry-run` ao doctor que tenta apenas abrir o socket sem chamar tools, para isolar problemas de rede vs. problemas de handler.
- **Recomendação**: pequena adição, atrelar a R6.

---

## 4. Itens que NÃO devem ser copiados

> Decisões consciente de não移植ar. Justificativa em cada caso, ligada a risco/contrato
> já documentado no servidor local.

| Item do hub remoto | Por que **não** copiar |
|---|---|
| Transporte UDP 7400/7401 | Quebra a premissa de loopback-only e o guard explícito em `client.py`; abre vetor LAN sem autenticação (UDP é amplificável). |
| "Stable Live object IDs" como promessa forte | O Live API não fornece handles persistentes cross-session. Path-IDs já são honestos sobre isso (`docs/ARCHITECTURE.md` §"Path-Id Scheme"). Prometer IDs estáveis seria mentir ao usuário. |
| Max for Live como surface adapter | Perde acesso ao Python LOM completo (MIDI notes, batch undo, lifecycle); introduz dependência de "uma trilha com o Hub na Set" que conflita com o workflow atual do servidor local. |
| Dry-run como default universal | Vai contra o modelo mental atual: o servidor local é uma ferramenta que **faz** sob allowlist. Tornar tudo dry-run por padrão dobraria a fricção. **Default seguro = allowlist + undo agrupado**, não dry-run. |
| Modelo "alpha público sem garantia" como contrato | O servidor local já está em v0.5.1 com 65 ferramentas estáveis e certificação. Adotar tom "alpha" regrediria a comunicação. |
| Sem validação de plataforma além de Windows/Live 12.3.5 | O servidor local explicitamente valida Live 12.4.5b7 + Windows e documenta o caminho WSL. Não regredir essa validação. |
| Reads "do not intentionally modify" como garantia absoluta | O servidor local já tem reads que **não** escrevem (asserted pela arquitetura). Mas a fronteira está clara pelo allowlist, não por promessa — preferir o allowlist. |

---

## 5. Fases ranqueadas

> Ordem sugerida para implementação. Cada fase é um PR pequeno, testável, com critérios
> de aceitação próprios. Não acumular PRs sem merge entre fases.

### Fase 0 — Higiene (pré-requisito, não é melhoria nova)

- Nada de novo código. Garantir:
  - `git status` limpo no branch.
  - `python -m pytest -q --tb=line` passa.
  - `python scripts/coverage_check.py` passa.
  - `python -m ruff check` + `python -m mypy --strict ableton_mcp_server` passam.
  - `python -c "from ableton_mcp_server.server import mcp; print(len(mcp.list_tools()))"` retorna 65.

### Fase 1 — Identidade e observabilidade (R1, R4)

**Por que primeiro**: baixa risco, alto ganho de auditabilidade. Não toca allowlist nem transporte.

- **R1**: campo `resolved` opt-in em 3 ferramentas (smoke test em testes).
- **R4**: script gera `docs/api_capability_matrix.md` automaticamente e CI falha se drift.
- Atualizar `AGENTS.md` linha sobre o que mudou.
- Atualizar `docs/TOOL_REFERENCE.md` com a coluna `stability` quando aplicável.

**Aceitação da Fase 1**:
- CI novo: `tests/test_capability_matrix.py` valida contagens (65 / 55 / 3).
- Três ferramentas emitem `resolved` em testes novos.
- Nenhuma regressão em `pytest`.

### Fase 2 — Segurança e instalação (R2, R3, R5, R6)

**Por que segundo**: endurecimento de segurança e install. Não muda runtime, só DX.

- **R2**: `dry_run=True` em 3–5 ferramentas caras, opt-in, documentado.
- **R3**: SHA-256 no `setup_windows.ps1`, seção "Verify Install" no README.
- **R5**: sumário executivo no topo de `KNOWN_BUGS.md` + link no README.
- **R6**: parâmetro `-DryRun` no `setup_windows.ps1`.

**Aceitação da Fase 2**:
- Documentação cruzada em `README.md`, `AGENTS.md`, `KNOWN_BUGS.md` consistente.
- Teste de SHA-256 sobre Remote Script versionado.
- Teste de `-DryRun` em `tests/test_setup_windows.py` (smoke).
- Teste de `dry_run=True` em pelo menos uma ferramenta.

### Fase 3 — Cobertura de domínio (E1 + extensões de busca)

**Por que terceiro**: funcionalidades que dependem do que foi consolidado nas Fases 1–2.

- Implementar `find_device` e `find_clip` (read-only) — pequeno.
- Avaliar `E5` (sample index) só depois dos itens anteriores fechados.

**Aceitação da Fase 3**:
- `find_device`/`find_clip` cobertos por testes com fakes (`tests/remote_fakes.py`).
- Sem mudanças em allowlist.

### Fase 4 — Specs abertas (E2–E6)

**Por que quarto**: cada item vira seu próprio design doc. **Nenhum é "automático"** — espera-se decisão humana antes de qualquer linha de código.

- Abrir `prompts/` ou `docs/superpowers/specs/` para `E1` (stable IDs — confirmar inviabilidade ou escopo), `E2` (UDP — descartar formalmente), `E3` (M4L — descartar formalmente), `E4` (clientes focados), `E5` (sample index), `E6` (doctor dry-run).

**Aceitação da Fase 4**:
- Specs publicadas com decisão registrada.
- Mudanças em código só se a spec for aprovada.

---

## 6. Critérios de aceitação transversais

Aplicam a **qualquer** fase que mexa em código:

1. **Sem mudança de contagem sem aviso**: o número 65 (ferramentas públicas) e 55 (comandos roteados) são invariantes para releases. Adicionar/renomear/remover tool exige update em `tests/test_server_tools.py`, `tests/test_tool_registry.py`, `tests/test_models.py`, `docs/TOOL_REFERENCE.md` e em `AGENTS.md`.
2. **Sem mudança em `_contracts.py`**: qualquer mudança em `contracts.py` regenera `_contracts.py` via `python scripts/vendor_contracts.py`. `tests/test_vendoring.py` deve passar.
3. **Sem chamar LOM da thread do socket**: o thread TCP só parseia/enfileira; `update_display()` da Remote Script avança. Verificar com grep que nenhum novo caminho toca `Song`/`Track`/`Clip`/etc. diretamente do socket thread.
4. **Erros estruturados**: bridge errors viram MCP error results tipados (`UNKNOWN_COMMAND`, `INVALID_PARAMS`, `STALE_REFERENCE`, etc.). Não introduzir crashes de framework.
5. **Loopback enforced**: cliente recusa host ≠ `127.0.0.1`. `tests/test_extension_loopback.py` deve continuar passando.
6. **Sem retry de mutação ambígua**: uma falha de conexão após mutação **não** reexecuta.
7. **Sem mudança silenciosa de undo**: `run_batch` continua sendo "grouped undo, not rollback". Nenhuma mudança pode introduzir replay reverso automático.
8. **Documentação canônica**: mudanças de comportamento vão em `README.md`/`docs/ARCHITECTURE.md`/`docs/TOOL_REFERENCE.md`/`docs/KNOWN_BUGS.md`, não em `.agent-context/` duplicado.
9. **Versões alinhadas**: bump de `pyproject.toml` + `manifest.json` + `AbletonMCPServer_Extension/package.json` em conjunto.
10. **Sem commit sem autorização explícita**: este documento é planejamento; nenhum dos itens das Fases 1–4 será commitado sem aprovação.

---

## 7. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Regressão em contagem 65 → quebrar consumers MCP | Média (Fase 1) | Alto | Testes de registry e contagem em CI; contagens expostas em capability matrix |
| Path-id estável prometido de forma falsa | Média (E1) | Alto | Documentar limitação explicitamente; preferir `find_*` sobre mudança de identidade |
| UDP exposto acidentalmente | Baixa (E2 já descartado) | Crítico | Manter guard em `client.py`; não copiar configuração de bind |
| M4L como adapter quebrando MIDI notes | Baixa (E3 já descartado) | Alto | Não migrar; documentar a razão em `docs/ARCHITECTURE.md` |
| Dry-run introduzido em tool que precisa ser síncrono | Média (Fase 2 / R2) | Médio | Limitar a 3–5 ferramentas, todas com `committed: false` no retorno; testar interação com `run_batch` |
| SHA-256 quebrar CI por mudança de whitespace no Remote Script | Baixa | Baixo | Regenerar hash em `tests/` quando o Remote Script muda intencionalmente |
| Doc drift entre `docs/api_capability_matrix.md` e o código | Média (Fase 1) | Médio | Script gerador + CI falha se drift |
| WSL launching path quebrado pela alteração em setup_windows.ps1 | Baixa (Fase 2) | Alto | `-WhatIf` nativo do PowerShell como baseline; `-DryRun` separado para testes manuais |

---

## 8. Referências verificáveis

> Cada referência aponta para um arquivo ou URL que pode ser aberto para confirmar a
> afirmação correspondente.

### 8.1 Repositório local `ableton-mcp-server`

- `AGENTS.md` — regras do repositório; 65 ferramentas; coupled-change rules; safety; WSL.
- `README.md` — superfície pública; FastMCP stdio + TCP 9888 + WS 9889; 65 ferramentas; WSL launching path; "Write-Then-Verify Loop".
- `docs/ARCHITECTURE.md` §"Components" — três componentes; mermaid do data flow.
- `docs/ARCHITECTURE.md` §"Socket Protocol" — framing ≤ 1 MiB; timeout; read retries; **nunca** retry de mutação.
- `docs/ARCHITECTURE.md` §"Mutation Allowlist" — `READ_COMMANDS`/`ALLOWED_MUTATIONS`/`READ_ONLY_COMMANDS`.
- `docs/ARCHITECTURE.md` §"Path-Id Scheme" — IDs são session-local locators, **não** handles.
- `docs/ARCHITECTURE.md` §"v0.5.0 set lifecycle…" — `lifecycle_status`, `save_set`, `quit_ableton`, `live_fade`, `create_audio_track`, `ableton_mcp_server.analysis`.
- `docs/ARCHITECTURE.md` §"v0.4.0 routing and capability boundaries" — 56 → 65 (via 9 v0.5.0 tools); device parameter writes verified; Session automation capability-gated.
- `docs/ARCHITECTURE.md` §"Error Model" — códigos tipados (`PLAYHEAD_NOT_MOVED`, `STALE_REFERENCE`, `EXTENSION_UNAVAILABLE`, etc.).
- `docs/ARCHITECTURE.md` §"Windows and WSL Process Topology" — `127.0.0.1:9888`; sem LAN; WSL lança `.exe` Windows.
- `docs/KNOWN_BUGS.md` Categorias A–G+ — deferred transport, toggle semantics, read-only props, missing methods, beat-time wrappers, protocol constants drift, session-local paths.
- `docs/INSPIRATION.md` — `pnomolos/live-wire`, `hidingwill/AbletonBridge`, `ideoforms/AbletonOSC`, `ideoforms/pylive`, `Simon-Kansara/ableton-live-mcp-server`. Design-only, **no code copy**.
- `docs/reports/2026-07-09-install-and-wsl-incompat.md` — instalação e incompatibilidade WSL (inclui F1: `hermes mcp test` não valida a bridge Live).
- `.agent-context/architecture.md` — boundary, components, routing, protocols, mutation lifecycle, identity, build/package.
- `.agent-context/hot-files.md` — `contracts.py`, `server.py`, `models.py`, `client.py`, `AbletonMCPServer_RemoteScript/__init__.py`, `AbletonMCPServer_Extension/src/index.ts`.
- `.agent-context/risks.md` — Python LOM thread affinity; WSL loopback ≠ Windows loopback; ambiguous mutation outcome; `run_batch` not rollback; duplicated contracts drift; path IDs session-local; deferred writes; Extension availability; acceptance testing mutates real Set.

### 8.2 Repositório remoto `ableton-agent-hub`

- README: https://github.com/8309/ableton-agent-hub — "Unofficial local Max for Live bridge and Python toolkit"; UDP `7400/7401`; "Mutating commands preview by default. `--commit` is required for a supported write."; "Stable Live object IDs preferred over changing track indices"; "A commit reads affected state back when the Live API permits it"; "Reads do not intentionally modify the Live Set"; "Unsupported writes fail rather than silently falling back to UI automation"; SHA-256 verify; "test on a copy".
- `docs/api_capability_matrix.md` — capability matrix (row-by-row source of truth).
- `docs/live_api_limits.md` — limites do Live API, áreas experimentais e bloqueadas.
- `docs/safety_model.md` — modelo de segurança completo.
- `docs/getting_started.md` — instalação customizada, troubleshooting, primeiro loop seguro.
- `docs/hub_workflow.md` — fluxo do Hub (Max modules ↔ built distribution ↔ installer resources).
- `docs/group_track_workflow.md`, `docs/manual_sample_workflow.md` — workflows específicos.
- `docs/release_scope_v0.1.0-alpha.md`, `docs/release_validation_v0.1.0-alpha.md` — escopo e validação da alpha.
- `ableton_agent/build_hub_device.py` — script de build do Hub.
- `ableton_agent/dist/`, `ableton_agent/max/`, `ableton_agent/sample_index/`, `ableton_agent/schemas/`, `ableton_agent/sound_catalog/`, `ableton_agent/styles/` — recursos auxiliares.
- `ableton_agent/python/ableton_bridge/` — clientes focados (módulos `track_management`, `parameter_summary`, `sample_confirm`).
- Commit alvo: `7ed73e42a726e5dc4a54759dda0bd09035c1bc3e` (HEAD `main`, tag `v0.1.0-alpha`).
- Idiomas: 58.9% JavaScript, 41.1% Python (verificado na barra de linguagens do GitHub).

### 8.3 Itens marcados como "[verificar]"

Os pontos abaixo **não** foram confirmados no snapshot atual do hub remoto (apenas leitura do
README e listagens de diretórios); antes de qualquer移植ação, abrir o arquivo correspondente
e validar:

- `[verificar]` conteúdo completo de `docs/api_capability_matrix.md` — quais linhas, quais categorias.
- `[verificar]` conteúdo completo de `docs/safety_model.md` — fluxos exatos de `--commit` e rollback.
- `[verificar]` `ableton_agent/python/ableton_bridge/` — lista de módulos expostos; flags aceitas; interfaces.
- `[verificar]` schema dos arquivos em `ableton_agent/schemas/` — podem inspirar tipagem local, mas não foram abertos.
- `[verificar]` comandos exatos em `ableton-agent.exe` além de `install`, `ping`, `tempo`, `raw`.

---

## 9. Conclusão

O `ableton-agent-hub` (v0.1.0-alpha) é uma referência interessante para **observabilidade**
(matriz de capability, sumário de limites, identidade estável em logs) e **segurança de
instalação** (SHA-256, dry-run install). Ele **não** é uma referência para o modelo de
transporte (UDP sem autenticação) nem para o surface adapter (Max for Live), porque o
servidor local já tem escolhas mais seguras e mais completas nessas duas dimensões.

Três melhorias pequenas e de baixo risco (`R1`, `R3`, `R4`) trazem a maior parte do valor
sem tocar o allowlist. As outras (`R2`, `R5`, `R6`) endurecem DX e segurança de instalação.
As ideias em aberto (`E1`–`E6`) precisam de specs dedicadas antes de qualquer implementação,
e várias já têm recomendação preliminar de **não copiar** com base em risco ou regressão
arquitetural.

Nada nesta lista será commitado sem autorização explícita. O próximo passo natural é
escolher a Fase 1 (`R1` + `R4`) como primeira entrega concreta, abrir um plano
`docs/superpowers/plans/2026-08-XX-phase-1-observability.md` e seguir o ciclo
plan → spec → implementação → revisão → merge.
