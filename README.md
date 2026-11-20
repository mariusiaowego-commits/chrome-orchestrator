# chrome-orchestrator

本地 Chrome 实例的调度层：**分类 → 归属 → 讲清楚 → 安全回收 → 唯一启动入口**。

macOS 上 Chrome 会被定时任务、agent、E2E 脚本、日常浏览同时启动。结果是：
孤儿 headless 进程、profile 互相污染、`ps | grep chrome` 误杀 Electron 应用、
以及「这个进程是谁开的」这个问题永远查不清。

本项目只做四件事：

1. **分类**：按可执行文件路径识别 Chrome 家族（系统 Chrome / Playwright Chromium /
   headless shell），明确排除 Electron、CEF 应用（ChatGPT、Obsidian、Battle.net 等）。
2. **归属**：把每个实例对到 `slots.toml` 里的槽位，记录启动事件到追加式台账。
3. **讲清楚**：输出一段大白话：谁开的、在做什么、为什么还活着、风险、建议。
4. **收口**：`chor spawn` 是唯一的启动入口（独立 profile + 固定端口），
   `chor reap` 是唯一的回收入口（先讲清楚它在做什么，再确认后收发信号）。

它**不**接管 uniservice 的端口注册表，也**不**做常驻 web 服务。

## 安装

```bash
uv venv
uv pip install -e .
chor --help
```

## 配置

```bash
mkdir -p ~/.config/chrome-orchestrator
cp slots.example.toml ~/.config/chrome-orchestrator/slots.toml
```

真实槽位配置只存在于用户目录，永不入库。

## 命令

| 命令 | 作用 |
|------|------|
| `chor ls` | 一行一个实例：端口、槽位、PID、存活时长、结论 |
| `chor explain <pid\|id\|slot>` | 单个实例的大白话档案（含 CDP 当前页面） |
| `chor status --json` | 稳定数据契约，供 uniservice-bar / 静态页消费 |
| `chor doctor` | 陈旧 SingletonLock、真实 profile 目录被写、同 profile 多实例 |
| `chor history <slot>` | 台账事件流 |
| `chor registry sync [--apply]` | 把带端口的槽位登记成 uniservice 的 `external` 条目 |
| `chor spawn --slot <name> [--headless]` | 按槽位启动唯一实例，profile 与端口都来自槽位 |
| `chor reap --pid <pid> [--yes]` | 预演后回收一棵 Chrome 进程树（默认不发信号） |

## 破坏性操作的边界

`ls` / `explain` / `status` / `doctor` / `history` / `slots` / `registry sync` 只读或只写自己的台账。

`spawn` 只写槽位自己的 `user_data_dir`，并且**拒绝**任何落在真实 Chrome 目录下的路径；
槽位没配 `user_data_dir` 时落到
`~/Library/Application Support/chrome-orchestrator/profiles/<slot>`。

`reap` 三档护栏，全部默认打开：

1. 不加 `--yes` 只打印计划（含当前打开的页面标题与 URL），不发信号。
2. 真实 profile（没传 `--user-data-dir`，或目录在系统 Chrome 根下）需要 `--allow-real-profile`。
3. 常驻槽位（`expect = "daemon"`）需要 `--allow-daemon`。

发信号前按 `pid + create_time` 复核进程身份，pid 被复用则中止；先 SIGTERM 让 Chrome
自己落盘，宽限期后仍未退出才 SIGKILL，子进程一起处理。

## 隐私边界

- 仓库只放通用代码、示例配置与合成测试数据。
- 运行期数据写入 `~/Library/Application Support/chrome-orchestrator/`。
- `scripts/check_pii.sh` 在 pre-commit 中拦截家目录绝对路径、用户名、
  主机名与常见 token 前缀；命中即失败。
- GitHub Actions 在每次 push / PR 运行同一套检查（Python 3.11 + Ubuntu）。
- 输出里的家目录统一缩写成 `~/`，不打印主机名。

## 数据契约

见 `docs/data-contract.md`。`schema_version` 变更视为破坏性修改。
