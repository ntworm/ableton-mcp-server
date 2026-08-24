"""Offline, length-prefixed subprocess adapter for an allowlisted provider."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

from .provider import (
    ProviderArtifactCandidate,
    ProviderConditionCardV1,
    ProviderFailure,
    ProviderFailureCode,
    ProviderLimitsV1,
    ProviderProtocolError,
    diagnostic_digest,
    sanitize_provider_diagnostic,
)
from .provider_registry import ProviderRegistry
from .resource_limits import (
    ResourceEnforcer,
    ResourceHandle,
    ResourceLimitUnavailable,
    select_resource_enforcer,
)

MAX_FRAME_BYTES = 256 * 1024
MAX_JSON_DEPTH = 8
_ALLOWED_METHODS = frozenset({"hello", "generate", "shutdown"})


def _json_depth(value: object, depth: int = 0) -> int:
    if isinstance(value, Mapping):
        return max([depth] + [_json_depth(item, depth + 1) for item in value.values()])
    if isinstance(value, list):
        return max([depth] + [_json_depth(item, depth + 1) for item in value])
    return depth


def encode_frame(payload: Mapping[str, object]) -> bytes:
    if not isinstance(payload, Mapping):
        raise ProviderProtocolError("frame payload must be an object")
    method = payload.get("method")
    if method is not None and method not in _ALLOWED_METHODS:
        raise ProviderProtocolError("unknown provider method")
    if _json_depth(payload) > MAX_JSON_DEPTH:
        raise ProviderProtocolError("frame depth exceeds limit")
    try:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProviderProtocolError("frame is not JSON serializable") from error
    if len(raw) > MAX_FRAME_BYTES:
        raise ProviderProtocolError("frame size exceeds limit")
    return struct.pack(">I", len(raw)) + raw


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ProviderProtocolError("provider closed the frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def decode_frame(stream: BinaryIO) -> Mapping[str, object]:
    header = _read_exact(stream, 4)
    (size,) = struct.unpack(">I", header)
    if size == 0 or size > MAX_FRAME_BYTES:
        raise ProviderProtocolError("frame size exceeds limit")
    try:
        decoded = json.loads(_read_exact(stream, size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderProtocolError("frame is not valid UTF-8 JSON") from error
    if not isinstance(decoded, dict):
        raise ProviderProtocolError("frame must contain a JSON object")
    if _json_depth(decoded) > MAX_JSON_DEPTH:
        raise ProviderProtocolError("frame depth exceeds limit")
    method = decoded.get("method")
    if method is not None and method not in _ALLOWED_METHODS:
        raise ProviderProtocolError("unknown provider method")
    return decoded


def build_allowlisted_environment(base: Mapping[str, str]) -> dict[str, str]:
    """Keep only the provider's non-secret, locale-stable process variables."""

    environment: dict[str, str] = {
        "PATH": str(base.get("PATH", os.defpath)),
        "TEMP": str(base.get("TEMP", tempfile.gettempdir())),
        "TMP": str(base.get("TMP", base.get("TEMP", tempfile.gettempdir()))),
        "PYTHONNOUSERSITE": "1",
        "LC_ALL": "C",
        "LANG": "C",
    }
    return environment


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate one provider process and its descendants without a shell."""

    pid = getattr(process, "pid", None)
    if pid is not None and os.name == "posix":
        with suppress(OSError, ProcessLookupError):
            killpg = getattr(os, "killpg", None)
            if callable(killpg):
                killpg(int(pid), 9)
    elif pid is not None and os.name == "nt":
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                shell=False,
                timeout=1.0,
            )
    try:
        process.terminate()
        process.wait(timeout=0.25)
    except (OSError, AttributeError, subprocess.TimeoutExpired):
        with suppress(OSError, AttributeError):
            process.kill()


class NeuralSubprocessProvider:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        provider_id: str,
        enforcer: ResourceEnforcer | None = None,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.registry = registry
        self.provider_id = provider_id
        self.enforcer = enforcer
        self.base_environment = dict(os.environ if base_environment is None else base_environment)

    def _failure(self, code: ProviderFailureCode, diagnostic: str = "") -> ProviderFailure:
        safe = sanitize_provider_diagnostic(diagnostic)
        return ProviderFailure(
            code=code,
            provider_id=self.provider_id,
            diagnostic_digest=diagnostic_digest(safe),
            diagnostic=safe,
        )

    def _read_with_timeout(self, stream: BinaryIO, timeout: float) -> Mapping[str, object]:
        result: list[Mapping[str, object]] = []
        error: list[BaseException] = []

        def read() -> None:
            try:
                result.append(decode_frame(stream))
            except BaseException as exc:  # pragma: no cover - thread boundary
                error.append(exc)

        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            raise TimeoutError("provider response deadline exceeded")
        if error:
            raise error[0]
        if not result:
            raise ProviderProtocolError("provider returned no frame")
        return result[0]

    @staticmethod
    def _send(process: subprocess.Popen[bytes], payload: Mapping[str, object]) -> None:
        if process.stdin is None:
            raise ProviderProtocolError("provider stdin is unavailable")
        process.stdin.write(encode_frame(payload))
        process.stdin.flush()

    @staticmethod
    def _validate_method(response: Mapping[str, object], method: str) -> None:
        if response.get("method") != method:
            raise ProviderProtocolError("provider method mismatch")
        if response.get("status") not in {"ok", "error"}:
            raise ProviderProtocolError("provider status is invalid")

    def generate(
        self,
        condition_card: ProviderConditionCardV1,
        parent_artifact_ids: tuple[str, ...],
        seed: int,
        limits: ProviderLimitsV1,
    ) -> ProviderArtifactCandidate | ProviderFailure:
        try:
            entry = self.registry.get(self.provider_id)
        except KeyError as error:
            return self._failure(ProviderFailureCode.not_installed, str(error))
        if (
            tuple(parent_artifact_ids) != condition_card.parent_artifact_ids
            or seed != condition_card.seed
        ):
            return self._failure(
                ProviderFailureCode.protocol_violation, "condition identity mismatch"
            )
        temp_dir = Path(tempfile.mkdtemp(prefix="groove-provider-"))
        process: subprocess.Popen[bytes] | None = None
        handle: ResourceHandle | None = None
        try:
            argv = [entry.executable, *entry.argv]
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                cwd=temp_dir,
                env=build_allowlisted_environment(self.base_environment),
                start_new_session=True,
            )
            enforcer = self.enforcer or select_resource_enforcer()
            handle = enforcer.enforce(process, limits)
            self._send(
                process,
                {
                    "method": "hello",
                    "schema_version": "groove.provider.hello.v1",
                    "provider_id": self.provider_id,
                },
            )
            hello = self._read_with_timeout(process.stdout, limits.startup_seconds)  # type: ignore[arg-type]
            self._validate_method(hello, "hello")
            if hello.get("status") != "ok":
                return self._failure(
                    ProviderFailureCode.protocol_violation, "provider hello failed"
                )
            self._send(
                process,
                {
                    "method": "generate",
                    "schema_version": "groove.provider.generate.v1",
                    "condition_card": condition_card.model_dump(mode="json"),
                    "parent_artifact_ids": list(parent_artifact_ids),
                    "seed": seed,
                    "limits": limits.model_dump(mode="json"),
                },
            )
            response = self._read_with_timeout(process.stdout, limits.generation_seconds)  # type: ignore[arg-type]
            self._validate_method(response, "generate")
            if response.get("status") != "ok":
                code = response.get("code")
                if isinstance(code, str) and code in {item.value for item in ProviderFailureCode}:
                    return self._failure(ProviderFailureCode(code), "provider rejected generation")
                return self._failure(
                    ProviderFailureCode.output_invalid, "provider rejected generation"
                )
            candidate = response.get("candidate")
            if not isinstance(candidate, Mapping):
                raise ValueError("provider candidate is missing")
            value = ProviderArtifactCandidate.model_validate(candidate)
            self._send(
                process,
                {"method": "shutdown", "schema_version": "groove.provider.shutdown.v1"},
            )
            self._read_with_timeout(process.stdout, limits.shutdown_seconds)  # type: ignore[arg-type]
            return value
        except FileNotFoundError as error:
            return self._failure(ProviderFailureCode.not_installed, str(error))
        except PermissionError as error:
            return self._failure(ProviderFailureCode.launch_denied, str(error))
        except ResourceLimitUnavailable as error:
            return self._failure(ProviderFailureCode.resource_limit, str(error))
        except TimeoutError as error:
            return self._failure(ProviderFailureCode.timeout, str(error))
        except ProviderProtocolError as error:
            return self._failure(ProviderFailureCode.protocol_violation, str(error))
        except (ValueError, TypeError) as error:
            return self._failure(ProviderFailureCode.output_invalid, str(error))
        except OSError as error:
            return self._failure(ProviderFailureCode.launch_denied, str(error))
        except Exception as error:  # pragma: no cover - defensive process boundary
            return self._failure(ProviderFailureCode.internal, type(error).__name__)
        finally:
            if process is not None:
                if handle is not None and self.enforcer is not None:
                    self.enforcer.terminate(handle)
                elif handle is not None:
                    (self.enforcer or select_resource_enforcer()).terminate(handle)
                else:
                    terminate_process_tree(process)
            with suppress(OSError):
                temp_dir.rmdir()


__all__ = [
    "MAX_FRAME_BYTES",
    "MAX_JSON_DEPTH",
    "NeuralSubprocessProvider",
    "ProviderProtocolError",
    "build_allowlisted_environment",
    "decode_frame",
    "encode_frame",
    "terminate_process_tree",
]
