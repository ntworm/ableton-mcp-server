from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ableton_mcp_server.groove_intelligence.provider import (
    ProviderFailure,
    ProviderFailureCode,
    build_condition_card,
    make_provider_limits,
    sanitize_provider_diagnostic,
)
from ableton_mcp_server.groove_intelligence.provider_registry import load_provider_registry
from tests.fixtures.groove_provider_payloads import (
    make_pilot_card_and_id,
)
from tests.fixtures.groove_provider_payloads import (
    make_provider_limits as fixture_limits,
)


def test_provider_request_contains_only_bounded_card_and_complete_identity(
    tmp_path: Path,
) -> None:
    card, artifact_id = make_pilot_card_and_id(tmp_path)
    request = build_condition_card(
        card,
        parent_artifact_ids=(artifact_id,),
        seed=7,
        limits=fixture_limits(),
    )
    serialized = request.model_dump_json().encode("utf-8")
    assert len(serialized) < 32 * 1024
    assert all(
        forbidden not in serialized
        for forbidden in (b"source_path", b"payload", b"sqlite", b"notes")
    )
    assert request.identity.model_digest == "sha256:" + "a" * 64


def test_registry_rejects_request_supplied_executable_and_unknown_failure_code(
    tmp_path: Path,
) -> None:
    path = tmp_path / "providers.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "provider_id": "p1",
                        "executable": "user.exe",
                        "argv": ["--bad"],
                        "executable_digest": "sha256:" + "a" * 64,
                        "version": "1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = load_provider_registry(path)
    assert registry.get("p1").argv == ("--provider-host",)
    with pytest.raises(ValidationError):
        ProviderFailure(code="command_from_request", provider_id="p1", diagnostic_digest="a" * 16)


def test_diagnostic_sanitization_removes_paths_and_secrets() -> None:
    assert sanitize_provider_diagnostic("C:\\Users\\me\\token=secret123") == (
        "<path> token=<redacted>"
    )


def test_provider_limits_are_bounded_and_failure_codes_are_closed() -> None:
    limits = make_provider_limits()
    assert limits.max_frame_bytes == 256 * 1024
    assert limits.max_events == 2048
    assert set(item.value for item in ProviderFailureCode) == {
        "not_installed",
        "launch_denied",
        "offline_policy",
        "protocol_violation",
        "timeout",
        "exit_nonzero",
        "output_too_large",
        "output_invalid",
        "resource_limit",
        "internal",
    }
