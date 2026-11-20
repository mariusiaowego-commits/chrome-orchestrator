from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import psutil
import pytest

from chrome_orchestrator import spawn
from chrome_orchestrator.config import Config
from chrome_orchestrator.model import Slot

FAKE_CHROME = """#!{python}
import http.server, sys, time
port = int(next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--remote-debugging-port=")))

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{{"Browser": "fake"}}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _slot(tmp_path: Path, **overrides) -> Slot:
    base = {
        "name": "scraper",
        "expect": "ondemand",
        "port": 19222,
        "user_data_dir": str(tmp_path / "profiles" / "scraper"),
    }
    base.update(overrides)
    return Slot(**base)


def test_argv_forces_own_profile_and_port(tmp_path: Path) -> None:
    slot = _slot(tmp_path)
    udd = spawn.resolve_udd(slot, ())
    argv = spawn.build_argv("/bin/chrome", slot, udd, headless=True)
    assert f"--user-data-dir={udd}" in argv
    assert "--remote-debugging-port=19222" in argv
    assert "--headless=new" in argv
    assert "--no-first-run" in argv


def test_slot_without_port_is_refused(tmp_path: Path) -> None:
    slot = _slot(tmp_path, port=None)
    with pytest.raises(spawn.SpawnError, match="没有配置端口"):
        spawn.build_argv("/bin/chrome", slot, "/tmp/x", headless=False)


def test_real_chrome_dir_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "Google" / "Chrome"
    slot = _slot(tmp_path, user_data_dir=str(real / "Default"))
    with pytest.raises(spawn.SpawnError, match="真实 Chrome 目录"):
        spawn.resolve_udd(slot, (real,))


def test_slot_without_udd_gets_project_profile_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHOR_PROFILE_ROOT", str(tmp_path / "chor-profiles"))
    slot = _slot(tmp_path, user_data_dir=None)
    assert spawn.resolve_udd(slot, ()) == os.path.realpath(tmp_path / "chor-profiles" / "scraper")


def test_spawn_refuses_port_already_listening(tmp_path: Path) -> None:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        busy = _slot(tmp_path, port=sock.getsockname()[1])
        with pytest.raises(spawn.SpawnError, match="已经有进程在监听"):
            spawn.spawn(busy, Config(slots=(busy,), real_roots=(), data_dir=tmp_path))


def test_spawn_records_ledger_and_reaches_cdp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake-chrome"
    fake.write_text(textwrap.dedent(FAKE_CHROME.format(python=sys.executable)))
    fake.chmod(0o755)
    monkeypatch.setenv("CHOR_CHROME_BIN", str(fake))

    slot = _slot(tmp_path, port=_free_port())
    cfg = Config(slots=(slot,), real_roots=(tmp_path / "Google",), data_dir=tmp_path / "data")
    result = spawn.spawn(slot, cfg, headless=True, wait=10.0)
    try:
        assert result["cdp_ready"] is True
        assert result["slot"] == "scraper"
        assert result["user_data_dir"].endswith("profiles/scraper")
        assert psutil.pid_exists(result["pid"])

        events = [
            json.loads(line)
            for line in (tmp_path / "data" / "events.jsonl").read_text().splitlines()
        ]
        assert [e["event"] for e in events] == ["spawned"]
        assert events[0]["slot"] == "scraper"
        assert events[0]["pid"] == result["pid"]
        assert events[0]["instance_id"] == result["instance_id"]
    finally:
        os.kill(result["pid"], 9)


def test_failed_start_cleans_up_its_own_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHOR_CHROME_BIN", sys.executable)
    slot = _slot(tmp_path, port=_free_port())
    with pytest.raises(spawn.SpawnError, match="没有开调试口"):
        spawn.spawn(
            slot,
            Config(slots=(slot,), real_roots=(), data_dir=tmp_path / "data"),
            headless=True,
            wait=1.0,
        )
    events = tmp_path / "data" / "events.jsonl"
    assert not events.exists()


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
