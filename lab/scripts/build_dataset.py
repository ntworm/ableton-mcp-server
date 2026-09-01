"""Entry point for a dataset build."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "lab"))

from groove_lab.dataset.build import build_dataset, manifest_digest  # noqa: E402
from groove_lab.dataset.config import BuildConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fraction", type=float, default=0.01)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--short-file-policy", default="looped")
    arguments = parser.parse_args()

    config = BuildConfig(short_file_policy=arguments.short_file_policy)
    manifest = build_dataset(arguments.fraction, config, arguments.workspace)
    print("counts               ", manifest.counts)
    print("representation loss  ", manifest.representation_loss)
    print("unresolved share     ", manifest.unresolved_note_share)
    print("largest cluster      ", manifest.cluster_sizes)
    print("excluded collections ", len(manifest.excluded_collections))
    print("manifest digest      ", manifest_digest(manifest))


if __name__ == "__main__":
    main()
