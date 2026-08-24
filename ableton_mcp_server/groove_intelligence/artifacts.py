"""Content-addressed local artifact stores for derived groove values."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import cast

from .canonical import canonical_json
from .runtime import ArtifactStore
from .schema import ArtifactId, MidiArtifactV1


class FileArtifactStore(ArtifactStore):
    """A host-selected local store; requests never provide its path."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        if not artifact_id.startswith("ga1_") or len(artifact_id) != 68:
            raise ValueError("invalid artifact id")
        return self.root / f"{artifact_id}.json"

    def put(self, artifact: MidiArtifactV1) -> ArtifactId:
        path = self._path(str(artifact.artifact_id))
        payload = artifact.model_dump(mode="python")
        blob = payload["payload"].get("blob")
        if isinstance(blob, bytes):
            payload["payload"]["blob"] = base64.b64encode(blob).decode("ascii")
        encoded = canonical_json(payload)
        temporary = path.with_suffix(".tmp")
        if not path.exists():
            temporary.write_bytes(encoded)
            os.replace(temporary, path)
        return artifact.artifact_id

    def get(self, artifact_id: str) -> MidiArtifactV1:
        path = self._path(artifact_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            blob = payload["payload"]["blob"]
            payload["payload"]["blob"] = base64.b64decode(blob, validate=True)
            return MidiArtifactV1.model_validate(payload)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KeyError(artifact_id) from error

    def contains(self, artifact_id: str) -> bool:
        try:
            return self._path(artifact_id).is_file()
        except ValueError:
            return False


class SeedBackedArtifactStore(ArtifactStore):
    """Read source artifacts lazily from an immutable seed; persist derivatives only."""

    def __init__(self, index: object, derived_root: Path) -> None:
        self.index = index
        self.derived = FileArtifactStore(derived_root)

    def get(self, artifact_id: str) -> MidiArtifactV1:
        if self.derived.contains(artifact_id):
            return self.derived.get(artifact_id)
        loader = getattr(self.index, "load_artifact", None)
        if not callable(loader):
            raise KeyError(artifact_id)
        try:
            return cast(MidiArtifactV1, loader(artifact_id))
        except (KeyError, ValueError) as error:
            raise KeyError(artifact_id) from error

    def put(self, artifact: MidiArtifactV1) -> ArtifactId:
        return self.derived.put(artifact)

    def contains(self, artifact_id: str) -> bool:
        if self.derived.contains(artifact_id):
            return True
        card_row = getattr(self.index, "card_row", None)
        if not callable(card_row):
            return False
        return card_row(artifact_id) is not None


__all__ = ["FileArtifactStore", "SeedBackedArtifactStore"]
