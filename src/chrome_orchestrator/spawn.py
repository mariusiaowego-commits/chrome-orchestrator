from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.request
from collections.abc import Sequence
from pathlib import Path

import psutil

from . import ledger
from .classify import classify_binary
from .config import Config
from .model import Event, Slot
from .scan import instance_id

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
)
DEFAULT_PROFILE_ROOT = "~/Library/Application Support/chrome-orchestrator/profiles"


class SpawnError(RuntimeError):
    """Refused or failed to start a Chrome instance."""


def chrome_binary() -> str:
    override = os.environ.get("CHOR_CHROME_BIN")
    if override:
        if not os.access(os.path.expanduser(override), os.X_OK):
            raise SpawnError(f"CHOR_CHROME_BIN 不可执行：{override}")
        return override
    for candidate in CHROME_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise SpawnError("找不到 Chrome 可执行文件，可用 CHOR_CHROME_BIN 指定")


def profile_root() -> Path:
    return Path(os.path.expanduser(os.environ.get("CHOR_PROFILE_ROOT") or DEFAULT_PROFILE_ROOT))


def resolve_udd(slot: Slot, real_roots: Sequence[Path]) -> str:
    """Where this slot is allowed to keep its profile. Never the real Chrome dir."""
    raw = slot.user_data_dir or str(profile_root() / slot.name)
    path = os.path.realpath(os.path.expanduser(raw))
    for root in real_roots:
        real_root = os.path.realpath(root)
        if path == real_root or path.startswith(real_root + os.sep):
            raise SpawnError(
                f"拒绝在真实 Chrome 目录启动：{path}\n槽位应指向独立 profile，别覆盖日常浏览数据。"
            )
    return path


def build_argv(binary: str, slot: Slot, udd: str, *, headless: bool) -> list[str]:
    if slot.port is None:
        raise SpawnError(f"槽位 {slot.name} 没有配置端口，无法给别的项目复用")
    argv = [
        binary,
        f"--user-data-dir={udd}",
        f"--remote-debugging-port={slot.port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        argv.append("--headless=new")
    return argv


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def cdp_ready(port: int, timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def wait_ready(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cdp_ready(port):
            return True
        time.sleep(0.25)
    return False


def caller_label() -> str:
    explicit = os.environ.get("CHOR_CALLER")
    if explicit:
        return explicit
    try:
        parent = psutil.Process(os.getppid())
        cmdline = " ".join(parent.cmdline()[:3])
        return f"ppid {os.getppid()} {cmdline}".strip()
    except (psutil.Error, OSError):
        return f"ppid {os.getppid()}"


def spawn(
    slot: Slot,
    cfg: Config,
    *,
    headless: bool = False,
    wait: float = 20.0,
    record: bool = True,
) -> dict:
    """Start exactly one Chrome for this slot, detached from the caller."""
    if slot.port is None:
        raise SpawnError(f"槽位 {slot.name} 没有配置端口")
    if port_in_use(slot.port):
        raise SpawnError(f":{slot.port} 已经有进程在监听；先 chor ls 确认是不是同一槽位")

    udd = resolve_udd(slot, cfg.real_roots)
    Path(udd).mkdir(parents=True, exist_ok=True)
    binary = chrome_binary()
    argv = build_argv(binary, slot, udd, headless=headless)
    caller = caller_label()

    proc = subprocess.Popen(  # noqa: S603 - argv built above, no shell
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=udd,
        start_new_session=True,
    )
    if not wait_ready(slot.port, wait):
        _discard(proc.pid)
        raise SpawnError(f"Chrome 在 {wait:.0f}s 内没有开调试口 :{slot.port}，已停掉刚起的进程")

    started_at = _create_time(proc.pid)
    inst_id = instance_id(classify_binary(binary) or "unknown-chromium", udd, started_at, binary)
    if record:
        ledger.append(
            [
                Event(
                    ts=time.time(),
                    event="spawned",
                    instance_id=inst_id,
                    pid=proc.pid,
                    slot=slot.name,
                    caller=caller,
                    note=f"mode={'headless' if headless else 'headed'} udd={udd}",
                )
            ],
            cfg.data_dir,
        )
    return {
        "pid": proc.pid,
        "instance_id": inst_id,
        "slot": slot.name,
        "port": slot.port,
        "user_data_dir": udd,
        "binary": binary,
        "headless": headless,
        "caller": caller,
        "cdp_ready": True,
    }


def _create_time(pid: int) -> float:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return time.time()


def _discard(pid: int) -> None:
    """Stop a process we just started ourselves; never touches anything else."""
    for sig in (15, 9):
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            return
        time.sleep(0.4)
