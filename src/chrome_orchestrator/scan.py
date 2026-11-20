from __future__ import annotations

import hashlib
import os
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

import psutil

from .classify import classify_binary, extract_port, extract_udd, is_helper, read_devtools_port
from .model import DUPLICATE_UDD, ORPHAN, REAL_PROFILE_WRITE, Instance, Proc, Slot


class ScanError(RuntimeError):
    """The OS refused to list processes (sandbox, seatbelt, EPERM)."""


def scan_processes() -> list[Proc]:
    procs: list[Proc] = []
    attrs = ["pid", "ppid", "create_time", "exe", "cmdline", "memory_info"]
    try:
        for proc in psutil.process_iter(attrs):
            try:
                info = proc.info
                cmdline = tuple(info.get("cmdline") or ())
                exe = info.get("exe") or (cmdline[0] if cmdline else "")
                mem = info.get("memory_info")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            procs.append(
                Proc(
                    pid=info["pid"],
                    ppid=info.get("ppid") or 0,
                    create_time=info.get("create_time") or 0.0,
                    exe=exe or "",
                    cmdline=cmdline,
                    rss_kb=int(mem.rss // 1024) if mem else 0,
                )
            )
    except PermissionError as exc:
        raise ScanError("无法读取进程列表：当前环境禁止 sysctl（沙箱 / seatbelt）") from exc
    return procs


def collect_instances(
    procs: Iterable[Proc],
    slots: Sequence[Slot],
    real_roots: Sequence[Path],
    now: float,
) -> list[Instance]:
    classified = [(p, k) for p in procs if (k := classify_binary(p.exe))]
    roots = [(p, k) for p, k in classified if not is_helper(p.cmdline)]
    helper_counts = Counter(p.ppid for p, _ in classified if is_helper(p.cmdline))
    udds = {p.pid: _normalize_udd(extract_udd(p.cmdline)) for p, _ in roots}
    udd_counts = Counter(u for u in udds.values() if u)

    instances: list[Instance] = []
    for proc, kind in roots:
        udd = udds[proc.pid]
        port = extract_port(proc.cmdline)
        if port == 0 and udd:
            port = read_devtools_port(udd)
        slot = _match_slot(slots, port, udd)

        flags: list[str] = []
        if udd and _under_any(udd, real_roots):
            flags.append(REAL_PROFILE_WRITE)
        if udd and udd_counts[udd] > 1:
            flags.append(DUPLICATE_UDD)
        # A slot is a declared owner: chor spawn detaches into ppid 1 by design,
        # so "detached" alone must not mean "nobody owns this".
        if proc.ppid == 1 and (udd or port) and not slot:
            flags.append(ORPHAN)

        instances.append(
            Instance(
                id=instance_id(kind, udd, proc.create_time, proc.exe),
                kind=kind,
                binary=proc.exe,
                user_data_dir=udd,
                port=port,
                root_pid=proc.pid,
                ppid=proc.ppid,
                started_at=proc.create_time,
                rss_kb=proc.rss_kb,
                helpers=helper_counts.get(proc.pid, 0),
                slot=slot,
                flags=flags,
            )
        )

    instances.sort(key=lambda i: (i.port is None, i.port or 0, i.root_pid))
    return instances


def stale_locks(real_roots: Sequence[Path]) -> list[dict]:
    """Find SingletonLock files whose owning pid is gone (crash or SIGKILL)."""
    found: list[dict] = []
    for root in real_roots:
        try:
            candidates = sorted(root.glob("*/SingletonLock"))
        except OSError:
            continue
        for lock in candidates:
            try:
                target = os.readlink(lock)
            except OSError:
                continue
            _, _, pid_text = target.rpartition("-")
            pid = int(pid_text) if pid_text.isdigit() else None
            found.append(
                {
                    "profile": lock.parent.name,
                    "pid": pid,
                    "alive": _pid_alive(pid),
                }
            )
    return found


def instance_id(kind: str, udd: str | None, started_at: float, fallback: str = "") -> str:
    """Stable id for one run of an instance: same profile restarted gets a new id."""
    seed = f"{kind}|{udd or fallback}|{started_at:.0f}"
    return hashlib.sha1(seed.encode()).hexdigest()[:12]


def _normalize_udd(udd: str | None) -> str | None:
    return os.path.realpath(udd) if udd else None


def _under_any(path: str, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            if os.path.commonpath([path, str(root)]) == str(root):
                return True
        except ValueError:
            continue
    return False


def _match_slot(slots: Sequence[Slot], port: int | None, udd: str | None) -> Slot | None:
    for slot in slots:
        if port is not None and slot.port == port:
            return slot
    if not udd:
        return None
    for slot in slots:
        if slot.user_data_dir and os.path.realpath(slot.user_data_dir) == udd:
            return slot
    return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
