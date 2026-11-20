from __future__ import annotations

import os
import signal
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psutil

from .cdp import list_pages
from .model import Instance

IDENTITY_TOLERANCE = 0.5


class ReapError(RuntimeError):
    """Refused or failed to stop an instance."""


@dataclass(frozen=True)
class ProcRef:
    pid: int
    create_time: float


@dataclass(frozen=True)
class ReapPlan:
    pid: int
    create_time: float
    kind: str
    slot: str | None
    user_data_dir: str | None
    uptime_seconds: int
    rss_mb: float
    pages: tuple[dict[str, str], ...]
    targets: tuple[ProcRef, ...]

    @property
    def helper_count(self) -> int:
        return len(self.targets) - 1


def plan(
    pid: int,
    instances: Sequence[Instance],
    *,
    real_roots: Sequence[Path] = (),
    now: float | None = None,
    allow_real_profile: bool = False,
    allow_daemon: bool = False,
) -> ReapPlan:
    """Decide whether this pid may be stopped, and what to show the user first."""
    inst = next((i for i in instances if i.root_pid == pid), None)
    if inst is None:
        raise ReapError(f"PID {pid} 不是受管的 Chrome 根进程；先 chor ls 看具体 pid")
    if not allow_real_profile:
        if inst.user_data_dir is None:
            raise ReapError(
                f"PID {pid} 没有独立 profile（用的是 Chrome 默认目录），"
                "回收会动到日常浏览数据。确认要停请加 --allow-real-profile"
            )
        if _under_any(inst.user_data_dir, real_roots):
            raise ReapError(
                f"PID {pid} 在用系统 Chrome 目录，回收会动到日常浏览数据。"
                "确认要停请加 --allow-real-profile"
            )
    if inst.slot and inst.slot.expect == "daemon" and not allow_daemon:
        raise ReapError(
            f"PID {pid} 属于常驻槽位 {inst.slot.name}，按设计应保活。确认要停请加 --allow-daemon"
        )
    if not identity_ok(pid, inst.started_at):
        raise ReapError(f"PID {pid} 的身份已变化（进程已退出或 pid 被复用），拒绝回收")

    create_time = _create_time(pid)
    pages = tuple(list_pages(inst.port)) if inst.port else ()
    targets = (ProcRef(pid, create_time), *_descendants(pid))
    return ReapPlan(
        pid=pid,
        create_time=create_time,
        kind=inst.kind,
        slot=inst.slot.name if inst.slot else None,
        user_data_dir=inst.user_data_dir,
        uptime_seconds=int(max(0.0, (now or time.time()) - inst.started_at)),
        rss_mb=round(inst.rss_kb / 1024, 1),
        pages=pages,
        targets=targets,
    )


def apply(reap: ReapPlan, *, grace: float = 8.0) -> dict:
    """SIGTERM the tree, give it time to flush profiles, then SIGKILL survivors."""
    if not identity_ok(reap.pid, reap.create_time):
        raise ReapError(f"PID {reap.pid} 在执行前就变了，已中止，未发送任何信号")

    signalled: list[int] = []
    for ref in reap.targets:
        if _alive(ref):
            try:
                os.kill(ref.pid, signal.SIGTERM)
                signalled.append(ref.pid)
            except ProcessLookupError:
                continue

    deadline = time.time() + grace
    while time.time() < deadline and any(_alive(ref) for ref in reap.targets):
        time.sleep(0.2)

    survivors = [ref for ref in reap.targets if _alive(ref)]
    for ref in survivors:
        try:
            os.kill(ref.pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
    if survivors:
        kill_deadline = time.time() + 2.0
        while time.time() < kill_deadline and any(_alive(ref) for ref in survivors):
            time.sleep(0.1)

    return {
        "pid": reap.pid,
        "signalled": signalled,
        "escalated": bool(survivors),
        "killed": [ref.pid for ref in survivors],
        "remaining": [ref.pid for ref in reap.targets if _alive(ref)],
    }


def identity_ok(pid: int, create_time: float) -> bool:
    try:
        actual = psutil.Process(pid).create_time()
    except psutil.Error:
        return False
    return abs(actual - create_time) <= IDENTITY_TOLERANCE


def _descendants(pid: int) -> tuple[ProcRef, ...]:
    try:
        root = psutil.Process(pid)
        children = root.children(recursive=True)
    except psutil.Error:
        return ()
    refs = []
    for child in children:
        try:
            refs.append(ProcRef(child.pid, child.create_time()))
        except psutil.Error:
            continue
    return tuple(refs)


def _create_time(pid: int) -> float:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error as exc:
        raise ReapError(f"读不到 PID {pid} 的启动时间：{exc}") from exc


def _alive(ref: ProcRef) -> bool:
    if not identity_ok(ref.pid, ref.create_time):
        return False
    try:
        return psutil.Process(ref.pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _under_any(path: str | None, roots: Sequence[Path]) -> bool:
    if not path:
        return False
    real = os.path.realpath(path)
    for root in roots:
        real_root = os.path.realpath(root)
        if real == real_root or real.startswith(real_root + os.sep):
            return True
    return False
