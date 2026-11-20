from __future__ import annotations

from pathlib import Path

import pytest

from chrome_orchestrator import cli
from chrome_orchestrator.cli import _find_instance, main, status_payload
from chrome_orchestrator.config import Config
from chrome_orchestrator.model import Instance, Slot

SHELL = "/tmp/chrome-headless-shell"


def _instances() -> list[Instance]:
    slot = Slot(name="scraper", expect="daemon", port=9223, purpose="scrape")
    return [
        Instance(
            id="aaaaaaaaaaaa",
            kind="headless-shell",
            binary=SHELL,
            user_data_dir="/tmp/profiles/scraper",
            port=9223,
            root_pid=200,
            ppid=1,
            started_at=1000.0,
            helpers=2,
            slot=slot,
        ),
        Instance(
            id="bbbbbbbbbbbb",
            kind="system-chrome",
            binary="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            user_data_dir=None,
            port=None,
            root_pid=100,
            ppid=1,
            started_at=500.0,
        ),
    ]


def test_status_payload_contract() -> None:
    cfg = Config(
        slots=(), real_roots=(Path("/tmp/Chrome"),), data_dir=Path("/tmp/data"), configured=True
    )
    payload = status_payload(_instances(), cfg, now=4600.0)
    assert payload["schema_version"] == 1
    assert payload["configured"] is True
    assert len(payload["instances"]) == 2
    daily = payload["instances"][1]
    assert daily["verdict"] == "keep"
    assert daily["port"] is None
    assert daily["uptime_seconds"] == 4100
    keys = set(payload["instances"][0])
    assert {"id", "kind", "port", "pid", "orphan", "slot", "flags", "verdict"} <= keys


def test_selectors_resolve_by_pid_prefix_and_slot() -> None:
    instances = _instances()
    assert _find_instance(instances, "100").root_pid == 100
    assert _find_instance(instances, "aaaa").id == "aaaaaaaaaaaa"
    assert _find_instance(instances, "scraper").root_pid == 200
    assert _find_instance(instances, "nope") is None


def test_spawn_unknown_slot_exits_before_touching_processes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHOR_CONFIG", str(tmp_path / "missing.toml"))
    assert main(["spawn", "--slot", "nope"]) == 1
    assert "没有槽位 nope" in capsys.readouterr().err


def test_reap_dry_run_sends_no_signal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os

    import psutil

    pid = os.getpid()
    inst = Instance(
        id="abcdef123456",
        kind="headless-shell",
        binary="/tmp/chrome-headless-shell",
        user_data_dir="/tmp/profiles/x",
        port=None,
        root_pid=pid,
        ppid=1,
        started_at=psutil.Process(pid).create_time(),
        rss_kb=10 * 1024,
    )
    monkeypatch.setattr(cli, "scan_processes", lambda: [])
    monkeypatch.setattr(cli, "collect_instances", lambda *a, **k: [inst])
    monkeypatch.setenv("CHOR_DATA_DIR", str(tmp_path))

    assert main(["reap", "--pid", str(pid)]) == 3
    out = capsys.readouterr().out
    assert f"将回收 PID {pid}" in out
    assert "没有发送任何信号" in out
    assert psutil.pid_exists(pid)
