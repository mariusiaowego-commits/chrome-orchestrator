from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path

from .model import Event, Instance

MAX_BYTES = 5 * 1024 * 1024


def events_path(data_dir: Path) -> Path:
    return data_dir / "events.jsonl"


def append(events: Iterable[Event], data_dir: Path) -> None:
    events = list(events)
    if not events:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    path = events_path(data_dir)
    _rotate(path)
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def load(data_dir: Path) -> list[Event]:
    path = events_path(data_dir)
    if not path.is_file():
        return []
    out: list[Event] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
            out.append(Event(**raw))
        except (ValueError, TypeError):
            continue
    return out


def observe(instances: Sequence[Instance], data_dir: Path) -> list[Event]:
    """Record first sighting and exits so history survives ppid loss."""
    data_dir.mkdir(parents=True, exist_ok=True)
    state_file = data_dir / "seen.json"
    try:
        seen: dict[str, dict] = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}

    now = time.time()
    current = {inst.id for inst in instances}
    new_events: list[Event] = []

    for inst in instances:
        if inst.id in seen:
            seen[inst.id]["last_seen"] = now
            continue
        new_events.append(
            Event(
                ts=now,
                event="observed",
                instance_id=inst.id,
                pid=inst.root_pid,
                slot=inst.slot.name if inst.slot else None,
                caller=None,
                note=f"ppid={inst.ppid}",
            )
        )
        seen[inst.id] = {"pid": inst.root_pid, "first_seen": now, "last_seen": now}

    for inst_id in [i for i in seen if i not in current]:
        new_events.append(
            Event(
                ts=now,
                event="exited",
                instance_id=inst_id,
                pid=seen[inst_id].get("pid"),
                note="process no longer present",
            )
        )
        seen.pop(inst_id, None)

    append(new_events, data_dir)
    _atomic_write(state_file, json.dumps(seen, ensure_ascii=False))
    return new_events


def _rotate(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_BYTES:
            return
    except OSError:
        return
    os.replace(path, path.with_suffix(".jsonl.1"))


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
