# STATUS

最后更新：2026-11-20

## 当前版本

`0.3.0` — M3 spawn/reap（本分支待合并）

## 仓库状态

- 本地：`~/dev/chrome-orchestrator`
- 远程：`https://github.com/mariusiaowego-commits/chrome-orchestrator`（公开）
- 分支：`feat/m3-spawn-reap`
- 最近提交（main）：`6b7513a`
- 未提交改动：见 `git status`（M3 分支内）

## 最近验证

```
.venv/bin/python -m pytest        45 passed
.venv/bin/ruff check .            All checks passed!
.venv/bin/ruff format --check .   23 files already formatted
bash scripts/check_pii.sh         check_pii: clean
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
| M2 | bar Chrome 分区（只读看板） | PR #18 待合并（bar 仓） |
| M3 | `chor spawn` 唯一启动入口 + `chor reap` 安全回收 | 本分支待合并 |

## M2 补充

`chor status --json` 里 `instances` 用 `id`、`slots` 用 `name`，两者结构不同。
bar 端曾把两者塞进同一个 Codable（`key` 取 id），解码必失败；已拆成
`ChromeInstance` / `ChromeSlot` 两个模型，并加 `Tests/chrome_board_smoke.swift` 兜住契约漂移。
