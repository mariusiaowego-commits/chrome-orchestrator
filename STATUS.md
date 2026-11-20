# STATUS

最后更新：2026-11-20

## 当前版本

`0.3.0` — M3 spawn/reap（PR #5；合并后打 tag `v0.3.0`）

## 仓库状态

- 本地：`~/dev/chrome-orchestrator`
- 远程：`https://github.com/mariusiaowego-commits/chrome-orchestrator`（公开）
- 主分支：`main`
- 未提交改动：无（PR #5 合并后工作区干净）

## 最近验证

```
.venv/bin/python -m pytest        45 passed
.venv/bin/ruff check .            All checks passed!
.venv/bin/ruff format --check .   23 files already formatted
bash scripts/check_pii.sh         check_pii: clean
GitHub Actions (PR #5)            pass
```

实机（临时槽位 `smoke`，端口 9333，profile `/private/tmp/chor-smoke/profile`）：

```
chor spawn --slot smoke --headless   → PID 68048，CDP 就绪
chor ls                              → 保留 :9333 smoke system-chrome
chor reap --pid 68048                → 预演，exit 3，打印 1 个页面（chrome://newtab/）
chor reap --pid 68048 --yes          → SIGTERM 正常退出，8 个进程，remaining=0
chor history smoke                   → spawned / observed / reaped
```

护栏复核：`chor reap --pid 1281`（日常 Chrome）被默认拒绝（无独立 profile）；
`chor reap --pid 64582`（moni 常驻槽位）被默认拒绝（需 `--allow-daemon`）。

## 阻塞

无。

## 路线

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 只读巡检、槽位、台账、数据契约、PII 拦截 | 完成 |
| M1 | 登记 `external` 端口，uniservice-bar 零改动可见 | 完成 |
| M2 | bar Chrome 分区（只读看板） | 完成（bar PR #18） |
| M3 | `chor spawn` 唯一启动入口 + `chor reap` 安全回收 | 完成（PR #5） |

## 已知约束

- `chor status --json` 里 `instances` 用 `id`、`slots` 用 `name`，两者结构不同；
  bar 端用 `ChromeInstance` / `ChromeSlot` 两套模型，`Tests/chrome_board_smoke.swift` 兜契约漂移。
- `uv.lock` 里项目版本仍是 0.1.0（pypi TLS 抖动导致 `uv lock` 刷新失败），不影响安装。
- `reap` 对「没有独立 profile」的实例默认拦截：这类实例视觉上与日常浏览器无法区分。
