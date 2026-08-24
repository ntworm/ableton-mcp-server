"""Explicit process resource enforcement for the optional provider host."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from .provider import ProviderLimitsV1


class ResourceLimitUnavailable(RuntimeError):
    """The host cannot prove the requested process limits are attached."""


@dataclass
class ResourceHandle:
    process: Any
    native_handle: Any = None
    terminated: bool = False


class ResourceEnforcer(Protocol):
    @property
    def available(self) -> bool: ...

    def enforce(
        self, process: subprocess.Popen[bytes], limits: ProviderLimitsV1
    ) -> ResourceHandle: ...

    def terminate(self, handle: ResourceHandle) -> None: ...


class UnavailableEnforcer:
    available = False

    def enforce(
        self, process: subprocess.Popen[bytes], limits: ProviderLimitsV1
    ) -> ResourceHandle:
        del process, limits
        raise ResourceLimitUnavailable("resource enforcement is unavailable")

    def terminate(self, handle: ResourceHandle) -> None:
        _terminate_process(handle.process)
        handle.terminated = True


class PosixProcessGroupEnforcer:
    available = os.name == "posix"

    def enforce(
        self, process: subprocess.Popen[bytes], limits: ProviderLimitsV1
    ) -> ResourceHandle:
        if not self.available:
            raise ResourceLimitUnavailable("POSIX process groups are unavailable")
        pid = int(process.pid)
        try:
            setpgid = getattr(os, "setpgid", None)
            if not callable(setpgid):
                raise ResourceLimitUnavailable("os.setpgid is unavailable")
            cast_setpgid = setpgid
            cast_setpgid(pid, pid)
            resource_module = __import__("resource")
            if hasattr(resource_module, "prlimit"):
                resource_module.prlimit(
                    pid,
                    resource_module.RLIMIT_CPU,
                    (int(limits.cpu_seconds), int(limits.cpu_seconds) + 1),
                )
                resource_module.prlimit(
                    pid,
                    resource_module.RLIMIT_AS,
                    (limits.memory_mib * 1024 * 1024, limits.memory_mib * 1024 * 1024),
                )
        except (AttributeError, OSError, ValueError) as error:
            raise ResourceLimitUnavailable("POSIX process limits could not be attached") from error
        return ResourceHandle(process=process)

    def terminate(self, handle: ResourceHandle) -> None:
        if handle.terminated:
            return
        try:
            killpg = getattr(os, "killpg", None)
            if not callable(killpg):
                raise OSError("os.killpg is unavailable")
            killpg(int(handle.process.pid), int(getattr(signal, "SIGKILL", 9)))
        except (OSError, AttributeError, ProcessLookupError):
            _terminate_process(handle.process)
        handle.terminated = True


class WindowsJobObjectEnforcer:
    available = os.name == "nt"

    def __init__(self, kernel32: Any | None = None) -> None:
        self._kernel32 = kernel32
        if self._kernel32 is None and self.available:
            windll = getattr(ctypes, "windll", None)
            if windll is not None:
                self._kernel32 = windll.kernel32

    def enforce(
        self, process: subprocess.Popen[bytes], limits: ProviderLimitsV1
    ) -> ResourceHandle:
        if not self.available or self._kernel32 is None:
            raise ResourceLimitUnavailable("Windows Job Objects are unavailable")
        native = self._kernel32.CreateJobObjectW(None, None)
        if not native:
            raise ResourceLimitUnavailable("CreateJobObjectW failed")
        try:
            info = _job_limit_info(limits)
            ok = self._kernel32.SetInformationJobObject(
                native,
                9,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                raise ResourceLimitUnavailable("SetInformationJobObject failed")
            process_handle = getattr(process, "_handle", None)
            if process_handle is None:
                raise ResourceLimitUnavailable("provider process handle unavailable")
            if not self._kernel32.AssignProcessToJobObject(native, process_handle):
                raise ResourceLimitUnavailable("AssignProcessToJobObject failed")
        except Exception:
            self._kernel32.CloseHandle(native)
            raise
        return ResourceHandle(process=process, native_handle=native)

    def terminate(self, handle: ResourceHandle) -> None:
        if handle.terminated:
            return
        _terminate_process(handle.process)
        if self._kernel32 is not None and handle.native_handle:
            self._kernel32.CloseHandle(handle.native_handle)
        handle.terminated = True


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInfo(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimitInfo(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInfo),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _job_limit_info(limits: ProviderLimitsV1) -> _ExtendedLimitInfo:
    info = _ExtendedLimitInfo()
    info.BasicLimitInformation.LimitFlags = 0x2 | 0x100 | 0x2000
    info.BasicLimitInformation.PerJobUserTimeLimit = int(limits.cpu_seconds * 10_000_000)
    info.ProcessMemoryLimit = limits.memory_mib * 1024 * 1024
    info.JobMemoryLimit = limits.memory_mib * 1024 * 1024
    return info


def _terminate_process(process: Any) -> None:
    try:
        process.terminate()
        process.wait(timeout=0.25)
    except (OSError, subprocess.TimeoutExpired, AttributeError):
        with suppress(OSError, AttributeError, subprocess.TimeoutExpired):
            process.kill()


def select_resource_enforcer(platform: str | None = None) -> ResourceEnforcer:
    selected = sys.platform if platform is None else platform
    if selected == "win32":
        return WindowsJobObjectEnforcer()
    if selected.startswith(("linux", "darwin", "freebsd")):
        return PosixProcessGroupEnforcer()
    return UnavailableEnforcer()


__all__ = [
    "PosixProcessGroupEnforcer",
    "ResourceEnforcer",
    "ResourceHandle",
    "ResourceLimitUnavailable",
    "UnavailableEnforcer",
    "WindowsJobObjectEnforcer",
    "select_resource_enforcer",
]
