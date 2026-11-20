# STATUS

最后更新：2026-11-20

## 当前版本

`0.1.0` — M0 只读巡检（未发布）

## 仓库状态

- 本地：`~/dev/chrome-orchestrator`
- 远程：未创建（等 `gh auth login` 恢复后建公开仓）
- 分支：`main`
- 未提交改动：无

## 最近验证

```
.venv/bin/python -m pytest        19 passed
.venv/bin/ruff check .            All checks passed!
.venv/bin/ruff format --check .   16 files already formatted
bash scripts/check_pii.sh         check_pii: clean
```

本机实跑：`chor ls` 只识别 1 个 `system-chrome`；`chor doctor` 报 2 个陈旧 SingletonLock。

## 阻塞

`gh` 令牌失效（`The token in keyring is invalid`），无法创建远程仓与 PR。
恢复方式：`gh auth login -h github.com`。

## 路线

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 只读巡检、槽位、台账、数据契约、PII 拦截 | 完成 |
| M1 | 登记 `external` 端口，uniservice-bar 零改动可见 | 待开始 |
| M2 | bar Chrome 分区 + 安全回收 | 待开始 |
| M3 | `chor spawn` 唯一启动入口 | 待开始 |
