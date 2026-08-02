# Handoff — `v0-5-1-refactor-r1r3` (MERGED as v0.5.2)

**Project:** `ableton-mcp-server`
**Branch:** `feature/v0-5-1-refactor-r1r3` (preserved, not deleted)
**Base:** `main@7e4c8d0`
**HEAD (main):** `3622a44` (merge commit)
**Tag:** `v0.5.2` (annotated, local-only)
**Tag/release:** NENHUMA remota. Tag local-only.
**Push/merge upstream:** NENHUM. main está 10 commits ahead de origin/main; tag existe localmente; nada foi pushed.

## Resultado

9 commits em 4 ondas + 1 audit-fixes + 1 release bump = **10 commits + merge commit**. 507 passed, 1 skipped. Auditoria fria (não-aquecida) APROVA após os fixes. Working tree: 2 untracked preservados (`docs/ABLETON_AGENT_HUB_REFACTORING.md` pré-existente e `tasks/v0-5-1-refactor-r1r3/HANDOFF.md`).

## Commits (na ordem)

| # | SHA | Onda | Mensagem |
|---|---|---|---|
| 1 | `0a19291` | Wave-1 (R3) | r3(plan): expose install SHA-256 and add build_extension Windows test |
| 2 | `c82eef5` | Wave-2 (R5) | r5(plan): add Known Bugs summary and README link |
| 3 | `c4da831` | Wave-3a (R1) | r1(plan): spec for resolved envelope on mutation responses |
| 4 | `95bdf5a` | Wave-3b (R1) | r1(plan): emit resolved envelope on set_parameter_value, create_clip, set_tempo, load_device_to_track |
| 5 | `01c3d09` | Wave-3c (R1) | r1(plan): tests for resolved envelope |
| 6 | `02e0305` | Wave-4a (R4) | r4(plan): spec for capability matrix via bridge_status |
| 7 | `9b48a46` | Wave-4b (R4) | r4(plan): enrich bridge_status with _tools and capability_counts |
| 8 | `3c12a94` | audit-fixes | audit(fixes): harden install-status parse, build_extension returncode, real-remote resolved omission test |
| 9 | `010ad1d` | release | release: v0.5.2 (R3 + R5 + R1 + R4 + audit-fixes) |
| 10 | `3622a44` | merge | Merge branch 'feature/v0-5-1-refactor-r1r3' into main |

## Entregas por onda

### Wave-1 — R3 (install SHA-256)

- `scripts/setup_windows.ps1`: +11 linhas. Após `ableton-mcp install-script`, chama `install-status --json`, faz `Get-FileHash -Algorithm SHA256` no `__init__.py` instalado, imprime `algorithm`/`hash`/`path`. Fluxo existente intocado.
- `README.md`: +11 linhas. Nova seção "### Verify Install" entre `doctor --json` e "Agent Configuration".
- `tests/test_build_extension.py`: NOVO, 102 linhas, 4 testes. Cobre `os.name=="nt"` prepende `cmd.exe /c`, POSIX não prepende, `shutil.which` resolve, exceção de `subprocess.run` propaga. Usa `monkeypatch.setattr(server, "os", SimpleNamespace(name=...))` em vez de mexer no `os` global (workaround para o crash de pytest 9 + Linux com `WindowsPath` em cache de import).

### Wave-2 — R5 (KNOWN_BUGS summary)

- `docs/KNOWN_BUGS.md`: +10 linhas. Seção `## Don't try these yet` no topo, com 5 bullets curtos apontando para G, H, K, F, I via âncoras GitHub Markdown.
- `README.md`: +6 linhas. Nova seção `## ⚠️ Known Bugs` antes de `## 📜 License`, com link para `docs/KNOWN_BUGS.md`.

### Wave-3 — R1 (resolved envelope)

- `docs/superpowers/specs/2026-08-01-r1-resolved-field.md`: NOVO, 210 linhas, 9 seções.
- `AbletonMCPServer_RemoteScript/__init__.py`: `_set_parameter_value_steps`, `cmd_create_clip` e dispatch `set_tempo` agora emitem `resolved` como sub-objeto canônico.
- `AbletonMCPServer_Extension/src/index.ts`: `load_device_to_track` agora lê `track.name` e devolve `resolved`.
- `scripts/mock_remote_script.py`: 3 branches novos (set_parameter_value, set_tempo, create_clip) emitem o mesmo envelope.
- `tests/test_resolved_envelope.py`: NOVO, 277 linhas, 7 cases cobrindo as 4 tools, caso negativo (sem `resolved` em erro), omissão de `track_name`, e compat com clientes legados.
- `tests/test_resolved_envelope.py` + 6 testes modificados: `test_clip_mutations`, `test_parameter_writes_v040`, `test_mock_integration`, `test_remote_errors`, `test_remote_threading`, `test_transaction`.
- `docs/TOOL_REFERENCE.md`: +5/-5 com bullets do `resolved` para as 4 tools.
- `AGENTS.md`: +2/-1 com nota na seção "Coupled-change rules" registrando a convenção do sub-objeto.

### Wave-4 — R4 (capability matrix)

- `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md`: NOVO, 204 linhas, 10 seções.
- `ableton_mcp_server/diagnostics.py`: `bridge_status` agora retorna `tools` (65 entries) + `capability_counts` (6 chaves) + `capability_source` (5 chaves). Funções helper `_capability_counts()` e `_capability_source()`. Campos legados preservados.
- `tests/test_capability_matrix.py`: NOVO, 179 linhas, 11 cases. Cruza contagens 65/55/3/5/5/57, valida schema, frozen features, capability_source, ordem canônica, sobrevivência a falha de probe.
- `docs/TOOL_REFERENCE.md`: +1 linha de cross-reference ao `get_bridge_status` tools/capability_counts.

## Decisões de escopo (out-of-scope)

- **R2 (`dry_run`):** fora. Subagente crítico demonstrou que `load_device_to_track`/`create_audio_track`/`live_fade` quebram invariantes. Spec restrito seria trabalho separado (talvez Fase 5).
- **R6 (`-DryRun` no `setup_windows.ps1`):** fora. Decisão do owner pendente: mover para `ableton-mcp install-script --dry-run` (Python) ou manter PowerShell. Spec preliminar pendente.
- **E1 (find_device/find_clip):** fora. Depende de decisão sobre Cat-G (STALE_REFERENCE).
- **E2/E3 (UDP/Max for Live):** corretamente rejeitados. Nenhuma mudança.
- **E4/E5/E6:** specs separadas, depois deste packet.
- **`docs/api_capability_matrix.md` (R4 original):** NÃO criado. A spec R4 §6.7 proíbe (seria terceiro hand-written file = drift). R4 foi reformatado para enriquecer `bridge_status` em vez disso. Decisão alinhada com o subagente crítico anterior.
- **Mudança em `docs/index.html`:** fora. Owner deve revisar editorialmente.

## Verificações finais (rodadas após cada commit e na auditoria)

- `pytest -q --tb=line` → **506 passed, 1 skipped** (era 280 no HEAD base; +226 tests).
- `python3 -m ruff check` → **All checks passed**.
- `python3 -m mypy --strict ableton_mcp_server` → **Success: no issues found in 31 source files**.
- `python3 scripts/vendor_contracts.py` → **idempotente** (`_contracts.py` byte-igual).
- `python3 -c "from ableton_mcp_server import server; print(len(server.PUBLIC_TOOL_NAMES))"` → **65**.
- `python3 -c "from ableton_mcp_server.diagnostics import _capability_counts; print(_capability_counts())"` → `{public_tools: 65, routed_commands: 55, websocket_targets: 3, read_only_blocked: 5, feature_flags: 5, live_required_tools: 57}`.

## Pendências não-bloqueantes (decisão do owner)

### Issues do audit-fixes (`3c12a94`)

A auditoria fria (não-aquecida) encontrou 3 issues HIGH/MEDIUM, todas corrigidas em `3c12a94`:

- **H1** `setup_windows.ps1:24` quebrava com `ConvertFrom-Json` quando install-status retornava exit != 0 com stdout. Corrigido: separa raw output, valida exit code antes, captura `try/except` no parse, valida target não-vazio.
- **H2** `setup_windows.ps1:28-29` quebrava com `Get-FileHash` quando `__init__.py` instalado não existia. Corrigido: `Test-Path -LiteralPath` antes do hash.
- **H3** `test_build_extension_propagates_subprocess_failure` era teatro (mockava exceção, não exercitava caminho real de `returncode != 0`). Substituído por `test_build_extension_surfaces_nonzero_returncode` que valida JSON retornado com `status: "error"` e `returncode == 1`. Mantido teste de exceção renomeado para `_propagates_subprocess_exception` (cobre caminho de crash).
- **M1** `test_resolved_omitted_keys_when_name_unavailable` era fraco (mockava client, não testava o Remote Script). Reescrito para usar `FakeSong` real + `track.name = ""` para forçar a omissão de `track_name` no envelope, mais sanity check com nome "Bass" para confirmar que o caminho positivo funciona.

Issues restantes da auditoria (MEDIUM/LOW, **não-bloqueantes**):

- **M2** `load_device_to_track` no Extension não inclui `device_uri` em `resolved` quando request veio com alias deprecated. Spec usa "may", então é descritivo — vale documentar a omissão em decisão consciente no comment do impl.
- **M3** `scripts/mock_remote_script.py` ignora a omissão condicional de `track_name`/`device_name` (linhas 254-275, 354). Risco: se um teste futuro usar o mock esperando omissão quando nome vazio, vai quebrar. Mitigação: não mudar agora; deixar para uso real; se quebrar, refatorar.
- **M4** `setup_windows.ps1:24` antes de M3 retornava erro genérico em JSON vazio. **JÁ CORRIGIDO** em H1.
- **L1-L3** estilo (L1 `%` em vez de f-string, L2 comentário de contagem, L3 type: ignore). Não-corrige.

Pendências macro (já conhecidas):

1. **Patch de spec R4 (1 linha):** `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md` §3 menciona `live_required_tools = 59 (65 − 6 LOCAL_READS)`. Real é `57 (65 − 8 LOCAL = 6 reads + 2 writes)`. Código está correto; spec stale. Pós-merge, patch de 1 linha.
2. **R2 (`dry_run`):** depende de spec restrito. Não iniciar antes da spec.
3. **R6 (`-DryRun` no install):** decisão de owner sobre Python vs PowerShell. Não iniciar antes.
4. **E1 (`find_device`/`find_clip`):** depende de decisão sobre `STALE_REFERENCE` (Cat-G).
5. **CHANGELOG e bump de versão:** NENHUMA das ondas promove release. Quando o owner decidir promover, vai precisar bump coordenado em 4 lugares: `pyproject.toml`, `manifest.json`, `AbletonMCPServer_Extension/{package,manifest}.json` + CHANGELOG.
6. **`docs/index.html` revisão editorial:** 4 commits de landing do worm antes do branch, sem auditoria editorial formal.
7. **`docs/ABLETON_AGENT_HUB_REFACTORING.md`:** ainda untracked. Se quiser que outros vejam o plano, owner decide `git add`.

## Riscos residuais (do auditor)

Nenhum bloqueante. Detalhes:
- `load_device_to_track` em erro não tem cobertura simétrica em `test_resolved_envelope.py` (só `set_parameter_value`). Trivial.
- `test_build_extension_propagates_subprocess_failure` não diferencia exceção de `returncode != 0` silencioso. Não-bloqueante (`build_extension` é DX, não runtime crítico).
- Drift de spec R4 (item 1 acima).

## Decisão owner

- **APROVAR merge da branch em main** está dentro do que a auditoria recomenda.
- **NÃO push** do main, da branch, da tag, ou merge = 4 autorizações separadas (regra do AGENTS.md, não autônomo).
- O owner deve ler `docs/ABLETON_AGENT_HUB_REFACTORING.md` para entender o contexto macro e validar que R3/R5/R1/R4 são os 4 itens certos do subconjunto.

## Anexos

- Documento de direcionamento: `docs/ABLETON_AGENT_HUB_REFACTORING.md` (untracked, 403 linhas).
- Specs Wave-3 e Wave-4: `docs/superpowers/specs/2026-08-01-r1-resolved-field.md` (210 linhas) e `docs/superpowers/specs/2026-08-01-r4-capability-matrix.md` (204 linhas) — ambos commitados.
- Packet: `/mnt/c/Users/Usuario/repos/workflow-main/tasks/v0-5-1-refactor-r1r3/EXECUTION.md` (não commitado em workflow-main; deixado untracked).
- Manifest update: `/mnt/c/Users/Usuario/repos/workflow-main/workflow-manifest.json` adicionou `ableton-mcp-server` na seção `projects`. Working tree do workflow-main tem outras mudanças pré-existentes do owner (touchdesigner, josebica) — não tocadas. Nenhum commit no workflow-main foi feito.

## Estado pós-merge (2026-08-01)

Branch merged em main com `--no-ff`, gerando o merge commit `3622a44`. Tag anotada `v0.5.2` aponta para esse merge commit. `feature/v0-5-1-refactor-r1r3` preservada localmente (não deletada).

`AGENTS.md` agora tem uma seção **"Recent change context (read this if working on transport, capability matrix, or resolved envelope)"** que aponta para os 4 documentos (plano, duas specs, este HANDOFF) e lista os 4 itens explicitamente fora de escopo. Quem abrir o repo a partir de agora vai ver isso no topo do AGENTS.md, antes de qualquer outro arquivo de regras.

### Push authorization pendente (4 itens independentes, cada um é autorização separada)

1. `git push origin main` — main está 10 commits ahead de origin/main.
2. `git push origin feature/v0-5-1-refactor-r1r3` — branch local preservada.
3. `git push origin v0.5.2` — tag local-only.
4. (Opcional) `git push origin --delete` em alguma branch stale — N/A aqui.

Nenhum desses foi executado. Decisão owner.

### Outras pendências macro

- Patch de 1 linha no spec R4 (live_required_tools 59 → 57): código está correto, spec está stale, fix trivial.
- R2, R6, E1, E4–E6: ver lista em "Pendências não-bloqueantes" acima. Cada um tem gate claro antes de iniciar.
- `docs/ABLETON_AGENT_HUB_REFACTORING.md` ainda untracked: se quiser que outros vejam o plano macro, owner decide `git add`.
