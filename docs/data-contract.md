# 数据契约

`chor status --json` 是唯一的机器接口。`schema_version` 变化视为破坏性修改。

```json
{
  "schema_version": 1,
  "generated_at": "2026-01-01T10:00:00+08:00",
  "configured": true,
  "instances": [
    {
      "id": "4f2a9c1b7d3e",
      "kind": "headless-shell",
      "port": 9223,
      "pid": 4427,
      "ppid": 1,
      "detached": true,
      "orphan": false,
      "slot": "example-scraper",
      "user_data_dir": "~/chrome-profiles/example-scraper",
      "uptime_seconds": 9720,
      "rss_mb": 86.1,
      "helpers": 6,
      "flags": [],
      "verdict": "keep",
      "verdict_reason": "常驻槽位，按设计保活"
    }
  ],
  "slots": [
    {
      "name": "example-scraper",
      "owner": "example-project",
      "purpose": "example daily scrape",
      "expect": "daemon",
      "port": 9222,
      "user_data_dir": "~/chrome-profiles/example-scraper"
    }
  ]
}
```

## 字段

| 字段 | 说明 |
|---|---|
| `id` | 实例身份，`kind + user-data-dir + 启动时间` 的短哈希 |
| `kind` | `system-chrome` / `playwright-chromium` / `headless-shell` / `unknown-chromium` |
| `port` | `--remote-debugging-port`，或 `DevToolsActivePort` 文件里的值 |
| `detached` | `PPID=1`，父进程已退出 |
| `orphan` | 脱离父进程且不属于常驻槽位，可回收 |
| `slot` | 命中的槽位名，未命中为 `null` |
| `user_data_dir` | `~/` 缩写后的路径，未指定为 `null` |
| `helpers` | 直接子进程数（renderer / gpu / utility） |
| `flags` | `real-profile-write` / `duplicate-udd` / `orphan` |
| `verdict` | `keep` / `migrate` / `reap` / `ask` |

## 兼容规则

- 新增可选字段：不升版本。
- 删除字段、改语义、改 `verdict` 取值：升 `schema_version`，并在此文件记录迁移说明。
