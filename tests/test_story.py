from __future__ import annotations

from pathlib import Path

from chrome_orchestrator.model import ORPHAN, REAL_PROFILE_WRITE, Instance, Slot
from chrome_orchestrator.story import display_path, fmt_dur, render, verdict


def _instance(**kwargs) -> Instance:
    base = dict(
        id="abc123abc123",
        kind="headless-shell",
        binary="/tmp/chrome-headless-shell",
        user_data_dir="/tmp/profile",
        port=9223,
        root_pid=200,
        ppid=1,
        started_at=1000.0,
        rss_kb=2048,
        helpers=3,
    )
    base.update(kwargs)
    return Instance(**base)


def test_story_is_plain_language(tmp_path: Path) -> None:
    slot = Slot(name="scraper", purpose="每天抓一次列表页", owner="demo", expect="daemon")
    inst = _instance(slot=slot, flags=[])
    text = render(inst, [], now=1000.0 + 3 * 3600, pages=[])
    for fragment in ("谁开的", "做什么", "为什么还在", "用的哪个", "风险", "建议"):
        assert fragment in text
    assert "每天抓一次列表页" in text
    assert verdict(inst)[0] == "keep"
    assert "保留" in text


def test_orphan_with_real_profile_recommends_migration() -> None:
    inst = _instance(flags=[ORPHAN, REAL_PROFILE_WRITE])
    text = render(inst, [], now=1000.0, pages=[])
    assert verdict(inst)[0] == "migrate"
    assert "系统 Chrome 目录" in text


def test_display_path_hides_home() -> None:
    home = str(Path.home())
    assert display_path(f"{home}/Library/Application Support/Google/Chrome") == (
        "~/Library/Application Support/Google/Chrome"
    )
    assert display_path(None) is None


def test_duration_format() -> None:
    assert fmt_dur(59) == "0m"
    assert fmt_dur(3600 + 5 * 60) == "1h05m"
    assert fmt_dur(2 * 86400 + 3600) == "2d01h"


def test_daily_browser_is_explained_calmly() -> None:
    inst = _instance(kind="system-chrome", user_data_dir=None, port=None, flags=[])
    text = render(inst, [], now=1000.0 + 600, pages=[])
    assert "日常浏览" in text
    assert "没人回收" not in text
