from __future__ import annotations

from pathlib import Path

import pytest

from chrome_orchestrator import scan
from chrome_orchestrator.model import DUPLICATE_UDD, ORPHAN, REAL_PROFILE_WRITE, Proc, Slot
from chrome_orchestrator.scan import ScanError, collect_instances
from chrome_orchestrator.story import verdict

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HELPER = (
    "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework"
    "/Versions/1.0/Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper"
)
SHELL = (
    "/opt/ms-playwright/chromium_headless_shell-1223"
    "/chrome-headless-shell-mac-arm64/chrome-headless-shell"
)


def test_daily_browser_is_not_an_orphan(tmp_path: Path) -> None:
    procs = [Proc(100, 1, 1000.0, CHROME, (CHROME,))]
    [inst] = collect_instances(procs, [], [tmp_path], now=2000.0)
    assert inst.port is None
    assert inst.user_data_dir is None
    assert not inst.is_orphan
    assert verdict(inst)[0] == "keep"


def test_helpers_are_counted_not_listed(tmp_path: Path) -> None:
    procs = [
        Proc(100, 1, 1000.0, CHROME, (CHROME,)),
        Proc(101, 100, 1000.0, HELPER, (HELPER, "--type=renderer")),
        Proc(102, 100, 1000.0, HELPER, (HELPER, "--type=gpu-process")),
    ]
    [inst] = collect_instances(procs, [], [tmp_path], now=2000.0)
    assert inst.helpers == 2


def test_headless_instance_inside_real_profile_is_flagged(tmp_path: Path) -> None:
    real_root = tmp_path / "Chrome"
    profile = real_root / "Profile 7"
    profile.mkdir(parents=True)
    procs = [
        Proc(
            200,
            1,
            1000.0,
            SHELL,
            (SHELL, "--headless", f"--user-data-dir={profile}", "--remote-debugging-port=9223"),
        ),
    ]
    [inst] = collect_instances(procs, [], [real_root], now=2000.0)
    assert REAL_PROFILE_WRITE in inst.flags
    assert ORPHAN in inst.flags
    assert verdict(inst)[0] == "migrate"


def test_daemon_slot_suppresses_orphan_flag(tmp_path: Path) -> None:
    profile = tmp_path / "profiles" / "scraper"
    profile.mkdir(parents=True)
    slot = Slot(name="scraper", expect="daemon", port=9223, user_data_dir=str(profile))
    procs = [
        Proc(
            200,
            1,
            1000.0,
            SHELL,
            (SHELL, "--headless", f"--user-data-dir={profile}", "--remote-debugging-port=9223"),
        ),
    ]
    [inst] = collect_instances(procs, [slot], [tmp_path / "Chrome"], now=2000.0)
    assert inst.slot is slot
    assert ORPHAN not in inst.flags
    assert verdict(inst)[0] == "keep"


def test_ondemand_slot_is_owned_not_orphan(tmp_path: Path) -> None:
    profile = tmp_path / "profiles" / "xwatch"
    profile.mkdir(parents=True)
    slot = Slot(name="x-watch", expect="ondemand", port=9222, user_data_dir=str(profile))
    procs = [
        Proc(
            210,
            1,
            1000.0,
            SHELL,
            (SHELL, f"--user-data-dir={profile}", "--remote-debugging-port=9222"),
        ),
    ]
    [inst] = collect_instances(procs, [slot], [tmp_path / "Chrome"], now=2000.0)
    assert ORPHAN not in inst.flags
    assert verdict(inst)[0] == "keep"


def test_duplicate_user_data_dir(tmp_path: Path) -> None:
    profile = tmp_path / "profiles" / "shared"
    profile.mkdir(parents=True)
    procs = [
        Proc(300, 1, 1000.0, CHROME, (CHROME, f"--user-data-dir={profile}")),
        Proc(301, 1, 1001.0, CHROME, (CHROME, f"--user-data-dir={profile}")),
    ]
    instances = collect_instances(procs, [], [tmp_path / "Chrome"], now=2000.0)
    assert len(instances) == 2
    assert all(DUPLICATE_UDD in inst.flags for inst in instances)


def test_instance_id_changes_after_restart(tmp_path: Path) -> None:
    first = Proc(400, 1, 1000.0, CHROME, (CHROME,))
    second = Proc(401, 1, 1500.0, CHROME, (CHROME,))
    [a] = collect_instances([first], [], [tmp_path], now=1600.0)
    [b] = collect_instances([second], [], [tmp_path], now=1600.0)
    assert a.id != b.id


def test_scan_error_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(_attrs):
        raise PermissionError("sysctl blocked")

    monkeypatch.setattr(scan.psutil, "process_iter", deny)
    with pytest.raises(ScanError):
        scan.scan_processes()
