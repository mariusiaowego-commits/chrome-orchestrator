from __future__ import annotations

import json
import urllib.request


def list_pages(port: int, timeout: float = 0.6) -> list[dict[str, str]]:
    """Read open page targets from the DevTools endpoint. Read-only, best effort."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as resp:
            raw = json.load(resp)
    except (OSError, ValueError):
        return []
    return [
        {"title": str(item.get("title", "")), "url": str(item.get("url", ""))}
        for item in raw
        if item.get("type") == "page"
    ]
