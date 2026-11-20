from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from .model import DUPLICATE_UDD, ORPHAN, REAL_PROFILE_WRITE, Event, Instance

VERDICT_LABELS = {
    "keep": "保留",
    "migrate": "建议迁走",
    "reap": "可回收",
    "ask": "需确认",
}

RISK_TEXT = {
    REAL_PROFILE_WRITE: "正在往系统 Chrome 目录写数据，可能污染真实 profile",
    ORPHAN: "父进程已退出，没人回收",
    DUPLICATE_UDD: "同一个 profile 被多个实例打开",
}

KIND_TITLES = {
    "system-chrome": "Chrome（日常）",
    "playwright-chromium": "Playwright Chromium",
    "headless-shell": "headless shell",
    "unknown-chromium": "未知 Chromium",
}


def is_daily(inst: Instance) -> bool:
    return inst.port is None and inst.user_data_dir is None


def verdict(inst: Instance) -> tuple[str, str]:
    if REAL_PROFILE_WRITE in inst.flags:
        return "migrate", "把这个 profile 迁到独立目录后再启动"
    if ORPHAN in inst.flags:
        return "reap", "确认没有在跑的任务后回收"
    if inst.slot and inst.slot.expect == "daemon":
        return "keep", "常驻槽位，按设计保活"
    if inst.slot and inst.slot.expect == "ondemand":
        return "keep", "按需槽位，任务结束可以用 chor reap 停掉"
    if is_daily(inst):
        return "keep", "日常浏览器"
    return "ask", "有调试口或独立 profile，需要人工确认用途"


def render(
    inst: Instance,
    events: Sequence[Event],
    now: float,
    pages: Sequence[dict[str, str]] | None = None,
) -> str:
    code, reason = verdict(inst)
    title = inst.slot.name if inst.slot else KIND_TITLES.get(inst.kind, inst.kind)
    port = f":{inst.port}" if inst.port else "无调试口"
    uptime = fmt_dur(now - inst.started_at)
    head = f"● {port} · {title} · PID {inst.root_pid} · 已运行 {uptime}"

    own = [e for e in events if e.instance_id == inst.id]
    first_seen = next((e.ts for e in own if e.event == "observed"), None)
    if first_seen is not None:
        who = f"台账首次记录 {fmt_ts(first_seen)}（更早的启动者已不可考）"
    elif is_daily(inst):
        who = f"系统启动（Finder / Dock / 默认浏览器）；启动于 {fmt_ts(inst.started_at)}"
    elif inst.ppid == 1:
        who = f"父进程已退出（PPID=1）；启动于 {fmt_ts(inst.started_at)}"
    else:
        who = f"父进程 PID {inst.ppid}；启动于 {fmt_ts(inst.started_at)}"

    if is_daily(inst):
        doing = "日常浏览；没有开调试口"
    elif inst.slot and inst.slot.purpose:
        doing = inst.slot.purpose
    elif pages:
        doing = "；".join(p["title"] or p["url"] for p in pages[:2])
    else:
        doing = "未知（无槽位定义，也没有可读的调试口）"

    if is_daily(inst):
        why = "日常浏览器，PPID=1 属正常（由系统启动）"
    elif inst.slot and inst.slot.expect == "daemon":
        why = "常驻槽位，任务结束后按设计不退出"
    elif inst.slot and inst.slot.expect == "ondemand":
        why = "按需槽位，由 chor spawn 拉起，用不到时可以回收"
    elif inst.ppid == 1:
        why = "父进程退出后没人回收"
    else:
        why = "随父进程运行"

    profile = display_path(inst.user_data_dir) or "Chrome 默认目录（未指定 --user-data-dir）"
    risks = [RISK_TEXT[f] for f in inst.flags if f in RISK_TEXT] or ["未发现"]
    owner = f"（归属：{inst.slot.owner}）" if inst.slot and inst.slot.owner else ""

    lines = [
        head,
        f"  谁开的    {who}",
        f"  做什么    {doing}{owner}",
        f"  为什么还在 {why}",
        f"  进程类型  {inst.kind}（{inst.helpers} 个子进程）",
        f"  用的哪个  {profile}",
        f"  风险      {'；'.join(risks)}",
        f"  建议      {VERDICT_LABELS[code]} — {reason}",
    ]
    for page in list(pages or [])[:3]:
        lines.append(f"  当前页面  {page['title']} — {page['url']}")
    return "\n".join(lines)


def fmt_dur(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def fmt_ts(ts: float) -> str:
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


def display_path(path: str | None) -> str | None:
    if not path:
        return None
    home = str(Path.home())
    return f"~{path[len(home) :]}" if path.startswith(home) else path
