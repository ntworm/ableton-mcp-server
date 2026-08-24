from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from ableton_mcp_server.groove_intelligence.build import (
    authorize_input,
    build_seed_bundle,
    compile_one,
)
from ableton_mcp_server.groove_intelligence.index import write_index
from ableton_mcp_server.groove_intelligence.schema import BuildInput
from tests.fixtures.groove_smf import MINIMAL_TYPE1_SMF, MULTI_TRACK_SMF

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_pilot_bundle(tmp_path: Path, *, source_root_name: str = "corpus") -> Path:
    source_root = tmp_path / source_root_name
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "pilot-a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (source_root / "pilot-b.mid").write_bytes(MULTI_TRACK_SMF)
    inputs = [
        BuildInput(
            path=source_root / "pilot-a.mid",
            source_kind="author",
            license_id="private-full",
            redistribution="full",
        ),
        BuildInput(
            path=source_root / "pilot-b.mid",
            source_kind="author",
            license_id="private-derived",
            redistribution="derived_only",
        ),
    ]
    manifest = build_seed_bundle(
        input_root=source_root,
        inputs=inputs,
        output_dir=tmp_path / "bundle",
        build_config={"pilot": "v1"},
    )
    compiled = []
    for declared in inputs:
        authorized_input, token = authorize_input(
            source_root,
            declared.path,
            source_kind=declared.source_kind,
            license_id=declared.license_id,
            redistribution=declared.redistribution,
        )
        compiled.append(
            compile_one(authorized_input, build_id=manifest.build_id, authorized_source=token)
        )
    write_index(tmp_path / "bundle", compiled, manifest)
    return tmp_path / "bundle"


def run_pilot_cli(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "corpus"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pilot-a.mid").write_bytes(MINIMAL_TYPE1_SMF)
    (root / "pilot-b.mid").write_bytes(MULTI_TRACK_SMF)
    bundle = tmp_path / "cli-bundle"
    manifest = root / "pilot-manifest.json"
    manifest.write_text(
        json.dumps({"files": ["pilot-a.mid", "pilot-b.mid"]}),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_groove_seed.py",
            "--input-root",
            str(root),
            "--manifest",
            str(manifest),
            "--output",
            str(bundle),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return cast(dict[str, object], json.loads(completed.stdout))
