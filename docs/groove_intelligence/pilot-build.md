# Groove Intelligence pilot build

Phase 1 accepts only an explicitly listed pilot manifest. The builder validates
every regular MIDI file against the supplied root, resolves symlinks, applies
the fixed parser/SQLite/deflate limits, and writes a path-free manifest plus an
immutable SQLite seed. It never enumerates the root implicitly.

```powershell
.\.venv-win\Scripts\python.exe scripts/build_groove_seed.py `
  --input-root <pilot-root> `
  --manifest <pilot-root>\pilot-manifest.json `
  --output <bundle-dir>
```

The manifest and logical index digests, artifact ids, projection digests,
lineage digests, and payload digests are deterministic for identical bytes and
configuration. The source directory may be removed after the build; the seed
opens from its own portable files.

No full corpus scan is authorized by Phase 1. Enumeration of the private
corpus is a later separately gated operation, after two identical pilot builds
have passed and a new execution authorization is recorded.

