from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from chrome_orchestrator import reap
from chrome_orchestrator.model import Instance, Slot

SHELL = "/tmp/chrome-headless-shell"


def _instance(pid: int, started_at: float, **overrides) -> Instance:
    base = {
        "id": "abcdef123456",
        "kind": "headless-shell",
        "binary": SHELL,
        "user_data_dir": None,
        "port": None,
        "root_pid": pid,
        "ppid": 1,
        "started_at": started_at,
        "rss_kb": 80 * 1024,
    }
    base.update(overrides)
    return Instance(**base)


def test_unknown_pid_is_refused(tmp_path: Path) -> None:
    with pytest.raises(reap.ReapError, match="不是受管的 Chrome 根进程"):
        reap.plan(os.getpid(), [])


def test_real_profile_needs_explicit_flag(tmp_path: Path) -> None:
    real = tmp_path / "Google" / "Chrome"
    inst = _instance(
        os.getpid(), psutil.Process().create_time(), user_data_dir=str(real / "Default")
    )
    with pytest.raises(reap.ReapError, match="系统 Chrome 目录"):
        reap.plan(os.getpid(), [inst], real_roots=(real,))
    plan = reap.plan(os.getpid(), [inst], real_roots=(real,), allow_real_profile=True)
    assert plan.pid == os.getpid()


def test_default_chrome_profile_needs_explicit_flag() -> None:
    """日常 Chrome 不传 --user-data-dir；它就是真实 profile，必须默认拦住。"""
    inst = _instance(os.getpid(), psutil.Process().create_time(), user_data_dir=None)
    with pytest.raises(reap.ReapError, match="没有独立 profile"):
        reap.plan(os.getpid(), [inst])
    plan = reap.plan(os.getpid(), [inst], allow_real_profile=True)
    assert plan.user_data_dir is None


def test_daemon_slot_needs_explicit_flag() -> None:
    slot = Slot(name="moni", expect="daemon", port=9223)
    inst = _instance(
        os.getpid(), psutil.Process().create_time(), slot=slot, user_data_dir="/tmp/profiles/moni"
    )
    with pytest.raises(reap.ReapError, match="常驻槽位"):
        reap.plan(os.getpid(), [inst])
    plan = reap.plan(os.getpid(), [inst], allow_daemon=True)
    assert plan.slot == "moni"


def test_stale_identity_is_refused() -> None:
    inst = _instance(
        os.getpid(), psutil.Process().create_time() + 120, user_data_dir="/tmp/profiles/x"
    )
    with pytest.raises(reap.ReapError, match="身份已变化"):
        reap.plan(os.getpid(), [inst])


def test_apply_terminates_tree_and_reports() -> None:
    script = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "time.sleep(120)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.time() + 10
        while time.time() < deadline and not psutil.Process(proc.pid).children():
            time.sleep(0.05)
        created = psutil.Process(proc.pid).create_time()
        plan = reap.plan(proc.pid, [_instance(proc.pid, created, user_data_dir="/tmp/profiles/x")])
        assert plan.helper_count == 1

        result = reap.apply(plan, grace=5.0)
        assert result["remaining"] == []
        assert result["escalated"] is False
        proc.wait(timeout=5)
        assert not psutil.pid_exists(proc.pid)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_apply_aborts_when_identity_changed_before_signals() -> None:
    inst = _instance(os.getpid(), psutil.Process().create_time(), user_data_dir="/tmp/profiles/x")
    plan = reap.plan(os.getpid(), [inst])
    tampered = reap.ReapPlan(**{**plan.__dict__, "create_time": plan.create_time + 99})
    with pytest.raises(reap.ReapError, match="执行前就变了"):
        reap.apply(tampered)


def test_reap_row_says_what_the_pages_are(tmp_path: Path) -> None:
    inst = _instance(
        os.getpid(), psutil.Process().create_time(), port=None, user_data_dir="/tmp/profiles/x"
    )
    plan = reap.plan(os.getpid(), [inst])
    assert plan.pages == ()
    assert plan.rss_mb == 80.0
