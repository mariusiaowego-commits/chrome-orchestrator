from __future__ import annotations

from dataclasses import dataclass, field

# Instance flags. Keep these stable: they end up in status --json.
ORPHAN = "orphan"
REAL_PROFILE_WRITE = "real-profile-write"
DUPLICATE_UDD = "duplicate-udd"
STALE_LOCK = "stale-lock"


@dataclass(frozen=True)
class Slot:
    """A named place where a Chrome instance is allowed to live."""

    name: str
    purpose: str = ""
    owner: str = ""
    expect: str = "daemon"  # daemon | ondemand | manual
    port: int | None = None
    user_data_dir: str | None = None


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    create_time: float
    exe: str
    cmdline: tuple[str, ...]
    rss_kb: int = 0


@dataclass(frozen=True)
class Event:
    ts: float
    event: str
    instance_id: str
    pid: int | None = None
    slot: str | None = None
    caller: str | None = None
    note: str = ""


@dataclass
class Instance:
    id: str
    kind: str
    binary: str
    user_data_dir: str | None
    port: int | None
    root_pid: int
    ppid: int
    started_at: float
    rss_kb: int = 0
    helpers: int = 0
    slot: Slot | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def detached(self) -> bool:
        return self.ppid == 1

    @property
    def is_orphan(self) -> bool:
        return ORPHAN in self.flags
