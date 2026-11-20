from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .model import Slot

DEFAULT_CONFIG = "~/.config/chrome-orchestrator/slots.toml"
DEFAULT_DATA = "~/Library/Application Support/chrome-orchestrator"
DEFAULT_REAL_ROOTS = ("~/Library/Application Support/Google/Chrome",)


@dataclass(frozen=True)
class Config:
    slots: tuple[Slot, ...] = ()
    real_roots: tuple[Path, ...] = ()
    data_dir: Path = Path(".")
    configured: bool = False

    def slot_by_name(self, name: str) -> Slot | None:
        return next((s for s in self.slots if s.name == name), None)


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    raw = os.environ.get("CHOR_CONFIG") or path or DEFAULT_CONFIG
    cfg_path = Path(os.path.expanduser(str(raw)))
    data_dir = Path(os.path.expanduser(os.environ.get("CHOR_DATA_DIR") or DEFAULT_DATA))
    roots = tuple(Path(os.path.expanduser(p)) for p in DEFAULT_REAL_ROOTS)

    if not cfg_path.is_file():
        return Config(real_roots=roots, data_dir=data_dir, configured=False)

    data = tomllib.loads(cfg_path.read_text())
    slots = tuple(_slot(item) for item in data.get("slot", []))
    roots = tuple(
        Path(os.path.expanduser(str(p)))
        for p in data.get("real_user_data_roots", DEFAULT_REAL_ROOTS)
    )
    return Config(slots=slots, real_roots=roots, data_dir=data_dir, configured=True)


def _slot(raw: dict) -> Slot:
    udd = raw.get("user_data_dir")
    return Slot(
        name=str(raw["name"]),
        purpose=str(raw.get("purpose", "")),
        owner=str(raw.get("owner", "")),
        expect=str(raw.get("expect", "daemon")),
        port=raw.get("port"),
        user_data_dir=os.path.expanduser(str(udd)) if udd else None,
    )
