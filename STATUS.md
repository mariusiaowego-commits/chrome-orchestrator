# STATUS

最后更新：2026-11-20

## 当前版本

`0.2.0` — M1 uniservice 桥接（未发布）

## 仓库状态

- 本地：`~/dev/chrome-orchestrator`
- 远程：`https://github.com/mariusiaowego-commits/chrome-orchestrator`（公开）
- 分支：`main`
- 最近提交：`f39de2b`
- 未提交改动：无

## 最近验证

```
.venv/bin/python -m pytest        19 passed
.venv/bin/ruff check .            All checks passed!
.venv/bin/ruff format --check .   16 files already formatted
bash scripts/check_pii.sh         check_pii: clean
GitHub Actions (main)            success — PII / ruff / pytest on Python 3.11
```

本机实跑：`chor ls` 只识别 1 个 `system-chrome`；`chor doctor` 报 2 个陈旧 SingletonLock。
`chor registry sync --apply` 已登记 2 条 external 条目（9223 / 9224）；9222 因被
`chrome-debug.headless` 占用而跳过。

## 阻塞

无。CI 已启用并通过（run `f39de2b`）。

## 路线

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 只读巡检、槽位、台账、数据契约、PII 拦截 | 完成 |
| M1 | 登记 `external` 端口，uniservice-bar 零改动可见 | 完成 |
| M2 | bar Chrome 分区 + 安全回收 | 待开始 |
| M3 | `chor spawn` 唯一启动入口 | 待开始 |
