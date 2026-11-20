from __future__ import annotations

from pathlib import Path

from chrome_orchestrator.config import Config
from chrome_orchestrator.model import Slot
from chrome_orchestrator.registry_sync import Desired, add_command, desired_entries, plan


def _cfg(*slots: Slot) -> Config:
    return Config(slots=slots, real_roots=(), data_dir=Path("/tmp/data"), configured=True)


def test_only_slots_with_ports_become_entries() -> None:
    cfg = _cfg(
        Slot(name="scraper", port=9222, purpose="scrape"),
        Slot(name="manual", port=None, purpose="manual"),
    )
    assert desired_entries(cfg) == [Desired("scraper", 9222, "scrape")]


def test_missing_entries_are_added() -> None:
    actions = plan([Desired("scraper", 9222, "scrape")], [])
    assert actions == [
        {"action": "add", "service": "scraper", "port": 9222, "description": "scrape"}
    ]


def test_existing_entry_with_same_port_is_quiet() -> None:
    current = [{"project": "chrome-orchestrator", "service": "scraper", "port": 9222}]
    assert plan([Desired("scraper", 9222, "scrape")], current) == []


def test_port_change_is_a_conflict_not_an_overwrite() -> None:
    current = [{"project": "chrome-orchestrator", "service": "scraper", "port": 9222}]
    [action] = plan([Desired("scraper", 9300, "scrape")], current)
    assert action["action"] == "conflict"
    assert action["registered_port"] == 9222


def test_entries_from_other_projects_are_ignored() -> None:
    current = [{"project": "moni", "service": "web", "port": 8900}]
    assert plan([Desired("scraper", 9222, "scrape")], current) == [
        {"action": "add", "service": "scraper", "port": 9222, "description": "scrape"}
    ]


def test_port_claimed_by_another_project_is_not_duplicated() -> None:
    current = [{"project": "chrome-debug", "service": "headless", "port": 9222}]
    [action] = plan([Desired("x-watch", 9222, "x")], current)
    assert action == {
        "action": "port-taken",
        "service": "x-watch",
        "port": 9222,
        "owner": "chrome-debug.headless",
    }


def test_stale_entry_is_reported_not_deleted() -> None:
    current = [{"project": "chrome-orchestrator", "service": "old", "port": 9221}]
    [action] = plan([], current)
    assert action == {"action": "orphan", "service": "old", "port": 9221}


def test_add_command_uses_sanctioned_cli_and_marks_external(tmp_path: Path) -> None:
    cmd = add_command("/bin/uni", Desired("scraper", 9222, "scrape"), tmp_path)
    assert cmd[:3] == ["/bin/uni", "add", "chrome-orchestrator.scraper"]
    assert "--external" in cmd
    assert "--port" in cmd and "9222" in cmd
    assert "--workdir" in cmd and str(tmp_path) in cmd
