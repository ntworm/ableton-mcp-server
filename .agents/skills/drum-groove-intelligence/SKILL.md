---
name: drum-groove-intelligence
description: Use when an MCP agent must retrieve, compare, deterministically generate, preview-map, or guardedly apply drum-groove artifacts from the offline Groove Intelligence surface; not for generic Live MIDI editing or raw corpus work.
---

# Drum Groove Intelligence

Fluxo MCP: `search -> evidence -> generate/compare -> apply`. Trate
`artifact_id` como opaco e confirme o alvo e o `slot vazio` antes de aplicar.
Esta skill é somente orientação: não executa SQL nem comandos externos por conta
própria.

Keep Groove Intelligence local and card-based: the deterministic core is always
available, neural generation is optional and must fall back without changing the
response contract, and artifact/seed/cursor IDs are opaque.

Generation is reproducible from the seed, transforms, bundle, and parent IDs.
The primary source plus up to seven references form one bounded parent set;
incompatible PPQ, meter, or rights are explicit rejections, not silent
degradation. The six transform axes are `density`, `syncopation`, `swing`,
`microtiming`, `energy`, and `complexity`.

Before `groove_apply`, preview mapping and confirm the explicit track, clip slot,
kit profile, and (when needed) source track/channel. Commit once. A `partial` or
`unknown` receipt means inspect Live and do not retry.

Read [references/workflow.md](references/workflow.md) for the efficient MCP
workflow, taxonomy/projection details, bounds, and current V1 JSON envelopes.
