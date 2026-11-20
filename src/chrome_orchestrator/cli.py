from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from collections.abc import Sequence
from datetime import datetime

from . import ledger, reap, spawn
from .cdp import list_pages
from .config import Config, load_config
from .model import DUPLICATE_UDD, REAL_PROFILE_WRITE, Event, Instance
from .registry_sync import apply_actions, desired_entries, find_binary, load_status, plan
from .scan import ScanError, collect_instances, scan_processes, stale_locks
from .story import VERDICT_LABELS, display_path, fmt_dur, render, verdict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chor", description="Local Chrome instance orchestrator")
    parser.add_argument("--config", help="slots.toml path (default: ~/.config/chrome-orchestrator)")
    parser.add_argument("--no-record", action="store_true", help="do not append to the ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ls", help="one line per Chrome instance")
    status = sub.add_parser("status", help="machine-readable contract")
    status.add_argument("--json", action="store_true", help="emit JSON (the only format for now)")
    explain = sub.add_parser("explain", help="plain-language profile of one instance")
    explain.add_argument("selector", help="pid, instance id prefix, or slot name")
    spawn_cmd = sub.add_parser("spawn", help="start the one Chrome a slot owns")
    spawn_cmd.add_argument("--slot", required=True, help="slot name from slots.toml")
    spawn_cmd.add_argument("--headless", action="store_true", help="use --headless=new")
    spawn_cmd.add_argument("--json", action="store_true", help="machine-readable result")
    spawn_cmd.add_argument("--wait", type=float, default=20.0, help="seconds to wait for CDP")
    reap_cmd = sub.add_parser("reap", help="stop one instance: SIGTERM, then SIGKILL")
    reap_cmd.add_argument("--pid", type=int, required=True, help="root pid from chor ls")
    reap_cmd.add_argument("--yes", action="store_true", help="actually send signals")
    reap_cmd.add_argument("--json", action="store_true", help="machine-readable result")
    reap_cmd.add_argument("--grace", type=float, default=8.0, help="SIGTERM grace seconds")
    reap_cmd.add_argument(
        "--allow-real-profile", action="store_true", help="allow reaping a real Chrome profile"
    )
    reap_cmd.add_argument("--allow-daemon", action="store_true", help="allow reaping a daemon slot")
    sub.add_parser("doctor", help="stale locks, polluted profiles, duplicate user-data-dirs")
    history = sub.add_parser("history", help="ledger events for one slot")
    history.add_argument("slot")
    sub.add_parser("slots", help="configured slots")
    registry = sub.add_parser("registry", help="bridge slot ports into uniservice")
    registry_sub = registry.add_subparsers(dest="registry_cmd", required=True)
    sync = registry_sub.add_parser("sync", help="register slot ports as external entries")
    sync.add_argument("--apply", action="store_true", help="write to the uniservice registry")
    sync.add_argument("--json", action="store_true", help="machine-readable plan/result")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)

    if args.cmd == "slots":
        _print_slots(cfg)
        return 0
    if args.cmd == "history":
        _print_history(cfg, args.slot)
        return 0
    if args.cmd == "registry":
        return _registry_sync(cfg, apply=args.apply, as_json=args.json)
    if args.cmd == "spawn":
        return _spawn(cfg, args)

    now = time.time()
    try:
        procs = scan_processes()
    except ScanError as exc:
        print(f"chor: {exc}", file=sys.stderr)
        print("提示：在沙箱外运行，或给终端授予进程查看权限。", file=sys.stderr)
        return 2
    instances = collect_instances(procs, cfg.slots, cfg.real_roots, now)
    if not args.no_record:
        ledger.observe(instances, cfg.data_dir)

    if args.cmd == "status":
        if args.json:
            print(json.dumps(status_payload(instances, cfg, now), ensure_ascii=False, indent=2))
        else:
            _print_status_summary(instances)
        return 0
    if args.cmd == "ls":
        _print_table(instances, now)
        return 0
    if args.cmd == "explain":
        return _explain(instances, cfg, args.selector, now)
    if args.cmd == "doctor":
        _print_doctor(instances, cfg)
        return 0
    if args.cmd == "reap":
        return _reap(cfg, instances, args, now)
    return 2


def status_payload(instances: Sequence[Instance], cfg: Config, now: float) -> dict:
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "configured": cfg.configured,
        "instances": [_instance_dict(inst, now) for inst in instances],
        "slots": [
            {
                "name": s.name,
                "owner": s.owner,
                "purpose": s.purpose,
                "expect": s.expect,
                "port": s.port,
                "user_data_dir": display_path(s.user_data_dir),
            }
            for s in cfg.slots
        ],
    }


def _instance_dict(inst: Instance, now: float) -> dict:
    code, reason = verdict(inst)
    return {
        "id": inst.id,
        "kind": inst.kind,
        "port": inst.port,
        "pid": inst.root_pid,
        "ppid": inst.ppid,
        "detached": inst.detached,
        "orphan": inst.is_orphan,
        "slot": inst.slot.name if inst.slot else None,
        "user_data_dir": display_path(inst.user_data_dir),
        "uptime_seconds": int(max(0.0, now - inst.started_at)),
        "rss_mb": round(inst.rss_kb / 1024, 1),
        "helpers": inst.helpers,
        "flags": list(inst.flags),
        "verdict": code,
        "verdict_reason": reason,
    }


def _explain(instances: Sequence[Instance], cfg: Config, selector: str, now: float) -> int:
    target = _find_instance(instances, selector)
    if target is None:
        print(f"找不到实例：{selector}")
        return 1
    pages = list_pages(target.port) if target.port else []
    events = ledger.load(cfg.data_dir)
    print(render(target, events, now, pages))
    return 0


def _spawn(cfg: Config, args: argparse.Namespace) -> int:
    slot = cfg.slot_by_name(args.slot)
    if slot is None:
        known = "、".join(s.name for s in cfg.slots) or "（未配置任何槽位）"
        print(f"chor: 没有槽位 {args.slot}；已知槽位：{known}", file=sys.stderr)
        return 1
    try:
        result = spawn.spawn(
            slot,
            cfg,
            headless=args.headless,
            wait=args.wait,
            record=not args.no_record,
        )
    except spawn.SpawnError as exc:
        print(f"chor: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"已启动 {slot.name} · PID {result['pid']} · :{result['port']}（调试口已就绪）")
    print(f"  profile  {display_path(result['user_data_dir'])}")
    print(f"  程序     {result['binary']}")
    print(f"  调用方   {result['caller']}")
    print("  说明     独立 profile、独立会话；关掉终端也不会退出，用 chor reap 回收")
    return 0


def _reap(cfg: Config, instances: Sequence[Instance], args: argparse.Namespace, now: float) -> int:
    try:
        reap_plan = reap.plan(
            args.pid,
            instances,
            real_roots=cfg.real_roots,
            now=now,
            allow_real_profile=args.allow_real_profile,
            allow_daemon=args.allow_daemon,
        )
    except reap.ReapError as exc:
        print(f"chor: {exc}", file=sys.stderr)
        return 1

    if not args.yes:
        print(_describe_plan(reap_plan))
        print("\n以上是预演，没有发送任何信号；确认后加 --yes 再跑一次。")
        return 3

    try:
        result = reap.apply(reap_plan, grace=args.grace)
    except reap.ReapError as exc:
        print(f"chor: {exc}", file=sys.stderr)
        return 1
    if not args.no_record:
        ledger.append(
            [
                Event(
                    ts=time.time(),
                    event="reaped",
                    instance_id=_instance_id_of(instances, args.pid),
                    pid=args.pid,
                    slot=reap_plan.slot,
                    caller=os.environ.get("CHOR_CALLER"),
                    note=f"escalated={result['escalated']} remaining={len(result['remaining'])}",
                )
            ],
            cfg.data_dir,
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    how = "SIGTERM 后升级 SIGKILL" if result["escalated"] else "SIGTERM 正常退出"
    print(f"已回收 PID {args.pid}（{how}），含 {len(result['signalled'])} 个进程")
    if result["remaining"]:
        print(f"  ! 仍在运行：{result['remaining']}")
        return 1
    return 0


def _describe_plan(plan: reap.ReapPlan) -> str:
    title = f"PID {plan.pid} · {plan.slot or '无槽位'} · {plan.kind}"
    lines = [
        f"将回收 {title}，已运行 {fmt_dur(plan.uptime_seconds)}，占用 {plan.rss_mb:.0f}M",
        f"  profile    {display_path(plan.user_data_dir) or '未指定（Chrome 默认目录）'}",
        f"  子进程     {plan.helper_count} 个（渲染/GPU/网络等，会一起退出）",
    ]
    if plan.pages:
        lines.append(f"  正在打开   {len(plan.pages)} 个页面：")
        for page in plan.pages[:5]:
            lines.append(f"    - {page['title'] or '（无标题）'} — {page['url']}")
    else:
        lines.append("  正在打开   读不到调试口（可能没开端口，或已卡死）")
    lines.append("  动作       SIGTERM 让 Chrome 自己落盘，宽限后仍未退出则 SIGKILL")
    return "\n".join(lines)


def _instance_id_of(instances: Sequence[Instance], pid: int) -> str:
    return next((i.id for i in instances if i.root_pid == pid), "")


def _find_instance(instances: Sequence[Instance], selector: str) -> Instance | None:
    if selector.isdigit():
        pid = int(selector)
        return next((i for i in instances if i.root_pid == pid), None)
    for inst in instances:
        if inst.id.startswith(selector):
            return inst
    return next((i for i in instances if i.slot and i.slot.name == selector), None)


def _print_table(instances: Sequence[Instance], now: float) -> None:
    if not instances:
        print("没有发现 Chrome 家族进程")
        return
    header = ["结论", "端口", "槽位", "类型", "PID", "存活"]
    widths = [8, 7, 22, 18, 8, 10]
    print("  ".join(_pad(h, w) for h, w in zip(header, widths, strict=True)))
    for inst in instances:
        code, _ = verdict(inst)
        row = [
            VERDICT_LABELS[code],
            str(inst.port or "—"),
            inst.slot.name if inst.slot else "—",
            inst.kind,
            str(inst.root_pid),
            fmt_dur(now - inst.started_at),
        ]
        print("  ".join(_pad(_cut(c, w), w) for c, w in zip(row, widths, strict=True)))


def _print_doctor(instances: Sequence[Instance], cfg: Config) -> None:
    problems = 0

    locks = stale_locks(cfg.real_roots)
    dead = [lock for lock in locks if not lock["alive"]]
    if dead:
        problems += len(dead)
        print("陈旧 SingletonLock（持有进程已退出）：")
        for lock in dead:
            print(f"  {lock['profile']}  pid {lock['pid']}")

    polluted = [i for i in instances if REAL_PROFILE_WRITE in i.flags]
    if polluted:
        problems += len(polluted)
        print("正在写系统 Chrome 目录：")
        for inst in polluted:
            label = inst.slot.name if inst.slot else inst.kind
            print(f"  :{inst.port}  {label}  →  {display_path(inst.user_data_dir)}")

    duplicated = [i for i in instances if DUPLICATE_UDD in i.flags]
    if duplicated:
        problems += len(duplicated)
        print("同一 profile 被多个实例打开：")
        for inst in duplicated:
            print(f"  PID {inst.root_pid}  →  {display_path(inst.user_data_dir)}")

    print("未发现问题" if problems == 0 else f"共 {problems} 项需要处理")
    if not cfg.configured:
        print("提示：未找到 slots.toml，槽位归属全部显示为未定义")


def _print_slots(cfg: Config) -> None:
    if not cfg.slots:
        print("没有配置槽位。参考 slots.example.toml 创建 ~/.config/chrome-orchestrator/slots.toml")
        return
    for slot in cfg.slots:
        port = f":{slot.port}" if slot.port else "无端口"
        print(f"{slot.name}  {port}  {slot.expect}  {slot.purpose}")


def _registry_sync(cfg: Config, *, apply: bool, as_json: bool) -> int:
    binary = find_binary()
    if binary is None:
        print("chor: 找不到 uniservice，可用 CHOR_UNISERVICE_BIN 指定路径", file=sys.stderr)
        return 2
    desired = desired_entries(cfg)
    if not desired:
        print("chor: 没有带端口的槽位，先补 slots.toml", file=sys.stderr)
        return 1
    try:
        actions = plan(desired, load_status(binary))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"chor: {exc}", file=sys.stderr)
        return 2

    if as_json and not apply:
        print(json.dumps({"actions": actions}, ensure_ascii=False, indent=2))
        return 0
    _print_actions(actions)
    if not actions:
        return 0
    if not apply:
        print("\n以上是预演；加 --apply 才写入 uniservice 注册表。")
        return 0

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    results = apply_actions(binary, actions, cfg.data_dir)
    if as_json:
        print(json.dumps({"actions": actions, "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            state = "ok" if result.get("ok") else ("skipped" if result.get("skipped") else "failed")
            print(f"  {result.get('service')}: {state} {result.get('output', '')}".rstrip())
    return 0 if all(r.get("ok") or r.get("skipped") for r in results) else 1


def _print_actions(actions: Sequence[dict]) -> None:
    if not actions:
        print("注册表已与槽位一致，无需改动")
        return
    for action in actions:
        if action["action"] == "add":
            print(f"+ {action['service']}  :{action['port']}  登记为 external")
        elif action["action"] == "conflict":
            print(
                f"! {action['service']}  配置为 :{action['port']}，"
                f"注册表里是 :{action['registered_port']}（需人工处理，不自动改）"
            )
        elif action["action"] == "port-taken":
            print(f"! {action['service']}  :{action['port']} 已被 {action['owner']} 占用，跳过")
        else:
            print(f"- {action['service']}  :{action['port']}  注册表有、槽位里没有（不自动删）")


def _print_status_summary(instances: Sequence[Instance]) -> None:
    counts = {code: 0 for code in VERDICT_LABELS}
    for inst in instances:
        counts[verdict(inst)[0]] += 1
    print(f"共 {len(instances)} 个 Chrome 实例")
    for code, label in VERDICT_LABELS.items():
        if counts[code]:
            print(f"  {label}: {counts[code]}")


def _print_history(cfg: Config, slot_name: str) -> None:
    events = [e for e in ledger.load(cfg.data_dir) if e.slot == slot_name]
    if not events:
        print(f"槽位 {slot_name} 还没有台账记录")
        return
    for event in events:
        stamp = time.strftime("%m-%d %H:%M:%S", time.localtime(event.ts))
        pid = event.pid if event.pid is not None else "—"
        print(f"{stamp}  {event.event:<9} pid {pid}  {event.note}")


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _cut(text: str, width: int) -> str:
    if _width(text) <= width:
        return text
    out = ""
    for ch in text:
        if _width(out + ch) > width - 1:
            break
        out += ch
    return out + "…"
