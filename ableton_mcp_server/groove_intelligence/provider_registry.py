"""Local allowlist for optional provider executables."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from .schema import GrooveModel


class AllowlistedProviderV1(GrooveModel):
    provider_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    executable: str = Field(min_length=1, max_length=260)
    executable_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    version: str = Field(min_length=1, max_length=64)
    argv: tuple[str, ...] = ("--provider-host",)

    @field_validator("argv", mode="before")
    @classmethod
    def _fixed_argv(cls, _value: object) -> tuple[str, ...]:
        # A request or registry file cannot select arbitrary provider flags.
        return ("--provider-host",)


class ProviderRegistry:
    def __init__(self, providers: tuple[AllowlistedProviderV1, ...]) -> None:
        self.providers = providers
        self._by_id = {item.provider_id: item for item in providers}

    def get(self, provider_id: str) -> AllowlistedProviderV1:
        try:
            return self._by_id[provider_id]
        except KeyError as error:
            raise KeyError(f"provider is not allowlisted: {provider_id}") from error

    def __iter__(self) -> Iterator[AllowlistedProviderV1]:
        return iter(self.providers)


def load_provider_registry(path: Path) -> ProviderRegistry:
    """Load a bounded local registry; argv is always replaced by the fixed flag."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ProviderRegistry(())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("provider registry is unreadable") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        raise ValueError("provider registry must contain a providers list")
    if len(raw["providers"]) > 8:
        raise ValueError("provider registry exceeds eight entries")
    providers: list[AllowlistedProviderV1] = []
    for item in raw["providers"]:
        if not isinstance(item, dict):
            raise ValueError("provider registry entries must be objects")
        values: dict[str, Any] = {
            key: item[key]
            for key in ("provider_id", "executable", "executable_digest", "version")
            if key in item
        }
        providers.append(AllowlistedProviderV1.model_validate(values))
    if len({item.provider_id for item in providers}) != len(providers):
        raise ValueError("provider registry ids must be unique")
    return ProviderRegistry(tuple(providers))


__all__ = ["AllowlistedProviderV1", "ProviderRegistry", "load_provider_registry"]
