# 设计

## 问题

macOS 上 Chrome 由五类调用方共同启动：日常浏览、cron/定时抓取、CLI agent、
E2E 脚本、历史遗留。它们共享同一个 `~/Library/Application Support/Google/Chrome`
目录树，而 Chrome 的互斥粒度是 `--user-data-dir`。

由此产生四个具体故障：

1. 调用方把 `<系统 Chrome 目录>/Profile N` 当成 `--user-data-dir` 传入。Chrome 会在这个
   子目录里再建一套 `Default/`、`Local State`，于是「自动化 profile」和「真实登录态」
   互不相干，同时两个浏览器进程在同一个目录树里各写各的。
2. 父进程退出后实例继续运行（`PPID=1`），没有台账，事后无法回答「谁开的」。
3. 同一个 `--user-data-dir` 已有实例时，第二次启动会被 Chrome 转发给已有实例并弹出窗口，
   表现为「浏览器自己跳出来抢焦点」。
4. 按进程名清理会误杀 Electron / CEF 应用（ChatGPT、Obsidian、Battle.net 等）。

## 为什么不在 uniservice 里做

`uniservice` 是端口中心模型：注册表主键是 `(project, service, port)`，其巡检明确把
`chrome*/chromium` 判为 noise 丢弃（`src/uniservice/patrol.py` 的 `is_noise`）。
Chrome 实例没有稳定端口，核心资源是 profile 互斥与进程树生命周期，塞进去会扭曲它的抽象。

可复用的是 `uniservice/process_control.py` 的 `ProcessIdentity(pid + create_time)` 与
`terminate()`（身份校验 → 组信号 → 宽限 → SIGKILL）。本项目的回收动作将沿用同一套语义。

## 三层模型

| 层 | 内容 | 数据来源 |
|---|---|---|
| 分类 | 按可执行路径判定 Chrome 家族；Electron/CEF 直接排除 | `psutil` 的 `exe` |
| 槽位 | 命名位置：端口、`user-data-dir`、用途、归属、期望生命周期 | `~/.config/chrome-orchestrator/slots.toml` |
| 台账 | 追加式事件流：首次观察、退出 | `~/Library/Application Support/chrome-orchestrator/events.jsonl` |

实例身份 = `sha1(kind + user-data-dir + 启动时间)`，重启后自然换新 id。

## 结论规则

| 条件 | 结论 | 含义 |
|---|---|---|
| `user-data-dir` 位于真实 Chrome 目录内 | 建议迁走 | 正在污染真实 profile |
| `PPID=1` 且不属于常驻槽位 | 可回收 | 父进程退出后无人负责 |
| 命中 `expect = "daemon"` 的槽位 | 保留 | 常驻是设计行为 |
| 无端口、无 `user-data-dir` | 保留 | 日常浏览器 |
| 其余 | 需确认 | 有调试口或独立 profile，用途不明 |

## 只读边界（v0.1）

不杀进程、不启动进程、不修改任何 profile。唯一的写入是自己的台账目录。

## 路线图

- **M0（本版）**：分类、归属、大白话档案、`doctor`、台账、数据契约、PII 拦截。
- **M1**：把带端口的实例登记为 `uniservice` 的 `external` 条目，让 uniservice-bar 零改动可见。
- **M2**：`uniservice-bar` 增加 Chrome 分区，读 `chor status --json`；回收动作（CDP
  `Browser.close` → 组 SIGTERM → SIGKILL）。
- **M3**：`chor spawn --slot <name>` 作为唯一启动入口，写入归属台账。

## M1 桥接规则

`chor registry sync` 只做三件事，全部通过 `uniservice add --external` 官方入口：

1. 槽位有端口、注册表没有 → 登记（`chrome-orchestrator.<slot>`）。
2. 端口与注册表不一致 → 报冲突，不自动改。
3. 注册表有、槽位没有 → 只报告，不自动删（删除是整个项目级操作，需人工）。

登记 `external` 的含义是「这个端口有主，uniservice 不要启停它」。上下线状态仍由
uniservice 自己探测端口得出，因此不会产生「注册表说在跑、其实没跑」的漂移。
