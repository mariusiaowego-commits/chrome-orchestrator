from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config

PROJECT = "chrome-orchestrator"


@dataclass(frozen=True)
class Desired:
    service: str
    port: int
    description: str


def desired_entries(cfg: Config) -> list[Desired]:
    return [Desired(s.name, s.port, s.purpose) for s in cfg.slots if s.port]


def find_binary() -> str | None:
    candidates = [
        os.environ.get("CHOR_UNISERVICE_BIN"),
        os.path.expanduser("~/dev/uniservice/.venv/bin/uniservice"),
        shutil.which("uniservice"),
    ]
    return next((str(c) for c in candidates if c and Path(c).exists()), None)


def load_status(binary: str, timeout: float = 30.0) -> list[dict]:
    proc = subprocess.run(
        [binary, "status", "--json"], capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(f"uniservice status 失败: {proc.stderr.strip()[:200]}")
    data = json.loads(proc.stdout)
    return data if isinstance(data, list) else data.get("services", [])


def plan(desired: list[Desired], current: list[dict], project: str = PROJECT) -> list[dict]:
    keyed = {(c.get("project"), c.get("service")): c for c in current}
    foreign_ports = {
        c.get("port"): f"{c.get('project')}.{c.get('service')}"
        for c in current
        if c.get("project") != project and c.get("port")
    }
    actions: list[dict] = []
    for item in desired:
        hit = keyed.get((project, item.service))
        if hit is None:
            owner = foreign_ports.get(item.port)
            if owner:
                actions.append(
                    {
                        "action": "port-taken",
                        "service": item.service,
                        "port": item.port,
                        "owner": owner,
                    }
                )
            else:
                actions.append(
                    {
                        "action": "add",
                        "service": item.service,
                        "port": item.port,
                        "description": item.description,
                    }
                )
        elif hit.get("port") != item.port:
            actions.append(
                {
                    "action": "conflict",
                    "service": item.service,
                    "port": item.port,
                    "registered_port": hit.get("port"),
                }
            )
    wanted = {item.service for item in desired}
    for (proj, svc), entry in keyed.items():
        if proj == project and svc not in wanted:
            actions.append({"action": "orphan", "service": svc, "port": entry.get("port")})
    return actions


def add_command(binary: str, item: Desired, anchor: Path, project: str = PROJECT) -> list[str]:
    return [
        binary,
        "add",
        f"{project}.{item.service}",
        "--port",
        str(item.port),
        "--desc",
        item.description or item.service,
        "--external",
        "--bind",
        "127.0.0.1",
        "--workdir",
        str(anchor),
        "--json",
    ]


def apply_actions(
    binary: str, actions: list[dict], anchor: Path, timeout: float = 30.0
) -> list[dict]:
    results: list[dict] = []
    for action in actions:
        if action["action"] != "add":
            results.append({**action, "ok": False, "skipped": True})
            continue
        cmd = add_command(
            binary,
            Desired(action["service"], action["port"], action.get("description", "")),
            anchor,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        results.append(
            {
                "service": action["service"],
                "ok": proc.returncode == 0,
                "output": (proc.stdout or proc.stderr).strip()[:300],
            }
        )
    return results
