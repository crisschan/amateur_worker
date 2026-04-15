# Software Design Document — worker Agent

**Version:** 1.0  
**Date:** 2026-04-13  
**Status:** Draft

---

## 1. Overview

worker Agent 是一个交互式 AI 办公助手 CLI。它将本地 LLM（通过 Ollama）与一套工具连接起来，用于文件管理、邮件收发、日历调度、任务追踪和后台处理。用户在 REPL 中输入请求，Agent 进行推理、调用工具，并循环执行直到任务完成。

### 1.1 Goals

- 提供一个本地、自包含的办公助手，能够读写文档、收发邮件、管理日历与任务
- 通过自动压缩机制，在长会话中保持上下文可控
- 通过后台执行和子 Agent 委派，支持并行工作
- 模块化设计：每项功能均可独立禁用

### 1.2 Non-Goals

- 云端部署或多用户支持
- 图形界面或 Web 界面
- 对外部服务的写操作沙箱隔离（操作以用户账户权限执行）

---

## 2. Architecture

### 2.1 High-Level Structure

```
main.py
  └─ Agent (agent/agent.py)
       ├─ AgentConfig (agent/config.py)
       ├─ AgentLoop (agent/loop.py)
       │    └─ LoopConfig (middleware wiring)
       ├─ Tools
       │    ├─ Documents   (agent/tools/documents.py)
       │    ├─ Email       (agent/tools/email.py)
       │    ├─ Calendar    (agent/tools/calendar.py)
       │    ├─ Todo        (agent/tools/todo.py)
       │    ├─ Tasks       (agent/tools/tasks.py)
       │    ├─ Background  (agent/tools/background.py)
       │    ├─ Skills      (agent/tools/skills.py)
       │    └─ Subagent    (agent/tools/subagent.py)
       └─ Memory
            └─ CompactManager (agent/memory/compact.py)
```

### 2.2 Request Lifecycle

```
User types input
      │
      ▼
HumanMessage appended to history
      │
      ▼
AgentLoop.run(history)
  ┌───────────────────────────────────────┐
  │  Pre-call middleware                  │
  │  ├─ Drain background notifications   │
  │  ├─ Inject todo-nag (if due)         │
  │  └─ Run context compaction           │
  │                                       │
  │  LLM call → AIMessage                │
  │                                       │
  │  No tool calls? → return             │
  │                                       │
  │  Tool calls? → execute each          │
  │  └─ Append ToolMessage results       │
  │  └─ Loop back to pre-call            │
  └───────────────────────────────────────┘
      │
      ▼
Print final AIMessage to user
```

---

## 3. Components

### 3.1 Configuration — `agent/config.py`

`AgentConfig` 是一个 dataclass，保存所有运行时设置。所有功能开关和调参参数均在此定义。

| Field | Default | Purpose |
|---|---|---|
| `model` | `OLLAMA_MODEL` env 或 `kimi-k2.5:cloud` | Ollama 模型名称 |
| `base_url` | `OLLAMA_BASE_URL` env 或 `http://localhost:11434` | Ollama 端点 |
| `temperature` | `0.2` | LLM 采样温度 |
| `max_tokens` | `4096` | 每次 LLM 响应的最大 token 数 |
| `workdir` | `Path.cwd()` | 文档操作的默认根目录 |
| `workspace` | `None`（回退到 `workdir`） | 文件操作边界；所有文件 I/O 均限定在此范围内 |
| `context_threshold` | `50000` | 触发自动压缩的字符数阈值 |
| `keep_recent_tools` | `3` | 微压缩时保留的最近工具结果条数 |
| `todo_nag_interval` | `3` | 提醒模型更新待办事项的轮次间隔 |
| `enable_todo` | `True` | 内存中的待办列表 |
| `enable_tasks` | `True` | 持久化 JSON 任务存储 |
| `enable_email` | `True` | 邮件收发功能 |
| `enable_calendar` | `True` | 日历查询与事件管理 |
| `enable_skills` | `True` | 按需加载技能包 |
| `enable_background` | `True` | 后台异步任务执行 |
| `enable_subagent` | `True` | 子 Agent 委派 |
| `enable_compact` | `True` | 上下文压缩 |
| `email_host` | `EMAIL_HOST` env 或 `None` | IMAP/SMTP 服务器地址 |
| `email_port_imap` | `EMAIL_PORT_IMAP` env 或 `993` | IMAP 端口（SSL） |
| `email_port_smtp` | `EMAIL_PORT_SMTP` env 或 `587` | SMTP 端口（STARTTLS） |
| `email_user` | `EMAIL_USER` env 或 `None` | 邮件账户用户名 |
| `email_password` | `EMAIL_PASSWORD` env 或 `None` | 邮件账户密码；建议通过系统 keychain 提供 |
| `caldav_url` | `CALDAV_URL` env 或 `None` | CalDAV 服务器 URL |

派生路径（只读属性）：
- `effective_workspace` → 若设置了 `workspace` 则使用它，否则使用 `workdir`
- `skills_dir` → `workdir/skills`
- `tasks_dir` → `workdir/.tasks`
- `transcripts_dir` → `workdir/.transcripts`

**`AgentConfig.from_file(path)`** 从 `agent.json` 文件加载配置。文件中存在的键会覆盖 dataclass 默认值；未知键被静默忽略。路径字段（`workdir`、`workspace`）相对于配置文件所在目录解析。
```
__workdir主要用于__：

- 定义代理程序的工作根目录
- 构建系统目录路径（skills/、.tasks/、.transcripts/）
- 作为workspace的默认值

__workspace主要用于__：

- 文档操作的安全边界
- 所有文件操作的安全性验证
- 防止路径遍历攻击

__关键区别__：

- workdir是系统级配置，影响整个代理程序的运行环境
- workspace是文件操作的安全边界，保护文件系统安全
- 当workspace为None时，使用workdir作为默认工作空间

```
示例 `agent.json`：
```json
{
  "model": "qwen2.5",
  "workdir": ".",
  "workspace": "./documents",
  "enable_background": false,
  "context_threshold": 30000
}
```

加载优先级：**dataclass 默认值** < **agent.json 配置** < **CLI 参数**。

### 3.2 Agent — `agent/agent.py`

顶层类。负责持有 REPL 并组装所有子系统。

**初始化（`_build`）：**
1. 创建 `ChatOllama` 客户端
2. 构建文档工具（始终启用；是所有文件读写的基础）
3. 根据功能开关条件性地实例化各管理器（邮件、日历、待办、任务、后台、技能包、子 Agent）
4. 将所有已启用的工具绑定到客户端
5. 使用 `LoopConfig` 创建 `AgentLoop`
6. 构建系统提示词

**Public API：**

```python
agent = Agent(config)
agent.repl()                             # 交互式会话
agent.run_query("帮我整理今天的会议记录")   # 单次无状态查询
```

**系统提示词**由已启用的功能模块共同组装。每个管理器贡献一段简短的指引块。模型被要求直接执行操作，而非仅做解释。

### 3.3 Agent Loop — `agent/loop.py`

实现 LLM ↔ 工具调用循环。在会话轮次之间无状态；消息列表由调用方持有。

**`LoopConfig`** 用于注入可选的中间件：
- `compact_manager` — 处理上下文压缩
- `bg_manager` — 排空后台通知
- `todo_manager` — 追踪待办使用情况以触发提醒计数器
- `todo_nag_interval` — 提醒前的轮次数

**`AgentLoop.run(messages)`** — 执行一个完整的会话轮次，在模型停止请求工具后返回。

### 3.4 Document Tools — `agent/tools/documents.py`

始终启用。接受两个操作边界：
- `workdir` — 文档操作的默认目录
- `workspace` — 所有读写工具和路径检查的文件边界（未设置时默认为 `workdir`）

| Tool | Args | Notes |
|---|---|---|
| `read_document` | `path: str, limit: int = None` | 输出上限 50 KB；路径在 workspace 范围内校验；支持 .txt、.md、.docx、.pdf |
| `write_document` | `path: str, content: str` | 自动创建父目录；路径在 workspace 范围内校验 |
| `edit_document` | `path: str, old_text: str, new_text: str` | 替换首次出现的内容；路径在 workspace 范围内校验 |
| `list_documents` | `path: str = "."` | 列出目录下的文档文件，输出文件名及最后修改时间 |

**路径安全**（`_make_safe_path`）：解析路径并检查其是否在 `effective_workspace` 范围内。若不在范围内则抛出 `ValueError`。

### 3.5 Email Tools — `agent/tools/email.py`

通过本地邮件客户端接口（如 IMAP/SMTP）收发邮件。

| Tool | Args | Notes |
|---|---|---|
| `email_list` | `folder: str = "INBOX", limit: int = 20` | 列出最近邮件，返回发件人、主题、时间、是否已读 |
| `email_read` | `email_id: str` | 读取完整邮件正文（不含附件），输出上限 50 KB |
| `email_send` | `to: str, subject: str, body: str, cc: str = None, confirm: bool = False` | 两阶段发送：`confirm=False` 返回草稿预览；`confirm=True` 执行发送 |
| `email_reply` | `email_id: str, body: str, confirm: bool = False` | 回复指定邮件，自动填充收件人与主题；同样采用两阶段确认 |
| `email_search` | `query: str, folder: str = "INBOX"` | 按关键词、发件人或日期范围搜索邮件 |

**发送确认机制（两阶段执行）：** `email_send` 和 `email_reply` 采用两阶段执行。第一次调用时（`confirm=False`，默认值），工具返回带有 `status: "pending_confirmation"` 和草稿内容的 `ToolMessage`，模型据此向用户展示草稿并请求确认。用户回复"确认发送"后，模型携带 `confirm=True` 再次调用同一工具，此时才真正执行发送。`confirm` 参数未设为 `True` 时，工具绝不发出任何邮件。

### 3.6 Calendar Tools — `agent/tools/calendar.py`

通过本地日历接口（如 CalDAV）管理日程事件。

| Tool | Args | Notes |
|---|---|---|
| `calendar_list` | `start: str, end: str` | 列出时间范围内的事件，日期格式 `YYYY-MM-DD` |
| `calendar_get` | `event_id: str` | 获取单个事件的完整详情 |
| `calendar_create` | `title: str, start: str, end: str, attendees: list = None, location: str = None` | 新建事件；时间格式 `YYYY-MM-DDTHH:MM` |
| `calendar_update` | `event_id: str, title: str = None, start: str = None, end: str = None, attendees: list = None, location: str = None` | 更新事件字段；只传入需要修改的字段，未传入的字段保持不变 |
| `calendar_delete` | `event_id: str` | 删除事件；执行前要求用户确认 |
| `calendar_find_slot` | `duration_minutes: int, attendees: list, within_days: int = 7` | 在指定参与者的日程中查找空闲时段 |

### 3.7 Todo Manager — `agent/tools/todo.py`

内存中的待办列表，最多 20 条。进程退出后重置。

**Schema：**
```python
{"id": str, "text": str, "status": "pending" | "in_progress" | "completed"}
```

**约束：** 同一时间只允许一条记录处于 `in_progress` 状态。

**Tool：** `todo(items: list) → str` — 每次调用时替换整个列表。

**提醒机制：** `AgentLoop` 统计自上次 `todo` 调用以来的轮次数。当轮次数超过 `todo_nag_interval` 时，在下次 LLM 调用前以 `HumanMessage` 形式注入一条提醒。

### 3.8 Task Manager — `agent/tools/tasks.py`

持久化任务存储。每个任务以 JSON 文件保存在 `.tasks/` 目录中。

**Schema：**
```json
{
  "id": 1,
  "subject": "...",
  "description": "...",
  "status": "pending | in_progress | completed",
  "blockedBy": [2, 3],
  "blocks": [4],
  "owner": "...",
  "due_date": "YYYY-MM-DD"
}
```

**依赖图：** 双向维护。当任务 A 被设置为阻塞任务 B 时，B 的 `blockedBy` 会同步更新。当任务完成时，它会从所有其他任务的 `blockedBy` 列表中移除。

| Tool | Purpose |
|---|---|
| `task_create(subject, description, due_date)` | 创建新任务 |
| `task_update(task_id, status, add_blocked_by, add_blocks)` | 更新状态或依赖关系 |
| `task_list()` | 列出所有任务 |
| `task_get(task_id)` | 获取任务完整详情 |

### 3.9 Background Manager — `agent/tools/background.py`

在守护线程中运行耗时操作，使 Agent 可以继续处理其他请求。

**后台任务类型（`BackgroundOp`）：** 后台任务不再是任意 shell 命令，而是一组预定义的办公操作类型，通过枚举约束可执行范围：

```python
class BackgroundOp(TypedDict):
    type: Literal["email_batch_send", "email_export", "doc_export", "calendar_sync"]
    params: dict   # 各类型对应的参数，由具体操作类型校验
```

各操作类型对应的实际执行逻辑由各工具模块提供，Background Manager 负责调度和生命周期管理。

**执行流程：**
- `background_run(op_type: str, params: dict)` — 校验 `op_type` 是否在允许列表内，在守护线程中启动任务，立即返回 `task_id`（UUID[:8]）
- 线程调用对应工具模块的批处理入口，超时限制 300 秒，捕获输出（上限 50 KB），存储结果，并将通知加入队列
- 不允许的 `op_type` 立即返回错误，不启动线程

**典型后台操作：**

| `op_type` | `params` 示例 | 说明 |
|---|---|---|
| `email_batch_send` | `{emails: [{to, subject, body}]}` | 批量发送邮件（跳过单封确认，需用户在调用前统一确认） |
| `email_export` | `{folder, start, end, dest_path}` | 导出指定时间段的邮件到本地文档 |
| `doc_export` | `{src_path, format}` | 文档格式转换导出 |
| `calendar_sync` | `{calendar_id}` | 触发日历数据同步刷新 |

**通知排空：** 每次 LLM 调用前，`AgentLoop` 排空通知队列，并将已完成任务的摘要以 `HumanMessage` 形式注入。

**`check_background(task_id=None)`** — 返回单个或全部后台任务的状态。

### 3.10 Skill Loader — `agent/tools/skills.py`

**Layer 1（始终启用）：** 在启动时将技能名称和单行描述注入系统提示词。

**Layer 2（按需加载）：** `load_skill(name)` 在模型需要时返回完整的 SKILL.md 内容。

**SKILL.md 格式：**
```markdown
---
name: skill-name
description: One-line description
tags: tag1, tag2
---

## Full instructions...
```

技能包在启动时通过扫描 `skills/*/SKILL.md` 自动发现。

**办公场景技能包示例：**
- `email-templates` — 常用邮件模板（请假、会议邀请、周报等）
- `meeting-minutes` — 会议纪要生成格式规范
- `report-formatting` — 报告排版与结构指引
- `calendar-etiquette` — 日程安排最佳实践

### 3.11 Subagent — `agent/tools/subagent.py`

以全新上下文和精简工具集生成子 Agent，用于委派独立的子任务。

**子 Agent 工具集：** 仅限文档工具 + 技能包。有意不含邮件、日历、任务/待办、后台、压缩工具，也不允许递归派生子 Agent。邮件和日历工具被排除在外是为了防止子 Agent 在无父 Agent 监督的情况下执行真实的通信操作；如需邮件/日历相关的子任务，父 Agent 应自行处理并仅将纯文档处理部分委派给子 Agent。

**`task(prompt, description)`** — 创建子 `Agent`，运行至完成，将最终 `AIMessage` 内容作为字符串返回。

**隔离性：** 子 Agent 无法访问父 Agent 的消息历史，防止上下文泄漏和无限递归。

**典型委派场景：** 将"整理本月所有会议纪要并生成摘要报告"拆分为多个子任务，分别委派给子 Agent 并发处理。

### 3.12 Compact Manager — `agent/memory/compact.py`

三层策略防止上下文溢出。

**Layer 1 — 微压缩（每轮静默执行）：**
- 将旧的 `ToolMessage` 内容替换为单行占位符
- 保留最近 `keep_recent_tools` 条工具结果的完整内容
- 原地修改消息列表；无需 LLM 调用

**Layer 2 — 自动压缩（阈值触发）：**
- 当 `estimate_tokens(messages) > context_threshold` 时触发
- 将完整会话记录保存到 `.transcripts/transcript_{ts}.jsonl`（JSONL 格式）
- 调用 LLM 生成连续性摘要
- 将所有消息替换为 `[HumanMessage: 摘要] + [AIMessage: 确认]`

**Layer 3 — 手动压缩（模型发起）：**
- 模型调用 `compact(focus="...")` 工具
- 设置标志位；实际压缩在下次 LLM 调用前执行，确保工具结果被纳入摘要

**Token 估算：** `len(str(messages)) // 4`

---

## 4. Data Flows

### 4.1 Document Operations

```
Model calls read_document("reports/Q1_summary.docx")
  → _make_safe_path 校验路径在 workspace 范围内
  → 文件读取，输出上限 50 KB
  → ToolMessage 返回给模型
```

### 4.2 Email Send Flow（两阶段确认）

```
[第一阶段] Model calls email_send(to="boss@company.com", subject="Q1 Report", body="...", confirm=False)
  → 工具返回 ToolMessage: {status: "pending_confirmation", draft: {to, subject, body}}
  → 模型将草稿内容展示给用户并询问："请确认是否发送此邮件？"
  → 用户在 REPL 输入确认

[第二阶段] Model calls email_send(...same args..., confirm=True)
  → 工具执行 SMTP 发送
  → 返回 ToolMessage: {status: "sent", message_id: "..."}
  → 模型告知用户发送成功

[用户拒绝] 用户在 REPL 输入取消
  → 模型不再调用 email_send
  → 告知用户操作已取消
```

### 4.3 Background Task Lifecycle

```
Model calls background_run("批量导出本月邮件附件")
  → 安全检查通过
  → 守护线程启动，立即返回 task_id
  → [线程] 操作执行，结果存储，通知入队
  → [下一轮] AgentLoop 排空队列，注入 HumanMessage
  → 模型获知任务已完成
```

### 4.4 Context Compaction

```
[每轮执行]
  微压缩：旧工具结果 → 占位符

[当字符数 > 阈值]
  保存会话记录 → .transcripts/
  LLM 生成摘要
  消息重置为 [摘要, 确认]

[模型调用 compact()]
  设置标志 → 在下次 LLM 调用前执行压缩
```

### 4.5 Subagent Delegation

```
Model calls task("整理并汇总本月所有部门周报")
  → 子 Agent 创建（仅含文档工具 + 技能包）
  → 子 Agent 运行独立的 AgentLoop 直至完成
  → 子 Agent 最终 AIMessage 作为字符串返回
  → 父 Agent 以 ToolMessage 形式接收汇总结果
```

---

## 5. Security

### 5.1 Path Traversal

所有传递给文档工具的路径均会被解析，并检查是否在 `effective_workspace`（若设置了 `workspace` 则使用它，否则使用 `workdir`）范围内。超出 workspace 的路径在任何 I/O 发生前抛出 `ValueError`。

### 5.2 Email Send Confirmation

`email_send` 和 `email_reply` 采用两阶段执行（见§3.5）。首次调用（`confirm=False`）只返回草稿预览，不发送任何内容；仅当模型在用户明确确认后携带 `confirm=True` 再次调用时，才执行真正的 SMTP 发送。这确保了在任何代码路径下，未经用户确认的调用均不会发出邮件。

### 5.3 Calendar Delete Confirmation

`calendar_delete` 在删除事件前要求用户确认，防止误删日程。

### 5.4 Subagent Isolation

子 Agent 只接收文档和技能工具。它们无法创建任务、派生更多子 Agent 或访问父 Agent 的会话历史。

### 5.5 操作权限范围

Agent 以运行用户的账户权限执行所有操作：文件读写受限于 workspace 配置，但邮件发送和日历修改均使用用户的真实账户凭据。不存在额外的权限隔离层。这是本地单用户场景下的有意取舍，使用者应了解 Agent 可代表自己执行真实的通信和日程操作。

---

## 6. Error Handling

| Scenario | Behavior |
|---|---|
| 工具抛出异常 | 捕获后以错误字符串作为 `ToolMessage` 返回；模型可重试 |
| 操作超时（300s） | 返回 `"Error: Timeout (300s)"` |
| 后台任务超时 | 任务状态设置为 `"timeout"` |
| LLM 调用失败 | 异常传播到 REPL 并打印堆栈跟踪 |
| 路径超出 workspace | `ValueError` 作为工具错误返回 |
| 邮件发送失败 | SMTP 错误信息作为 `ToolMessage` 返回；模型可重试或通知用户 |
| 日历连接失败 | CalDAV 错误信息返回；模型提示用户检查网络或账户配置 |
| 用户拒绝确认（邮件/日历删除） | 工具返回 `status: "cancelled"`；模型向用户说明操作已取消，不再重试 |
| 邮件/日历凭据未配置 | 工具在初始化时抛出 `ConfigError`，Agent 启动时提示用户补全配置 |

不内置自动重试逻辑。模型收到错误后自行决定如何处理。

---

## 7. Extension Points

### 7.1 Adding a Tool

1. 创建 `agent/tools/my_tool.py`，包含 `@tool` 装饰的函数
2. 添加工厂函数 `create_my_tools(config) -> list`
3. 在 `Agent._build()` 中通过功能开关条件性地实例化
4. 添加到传递给客户端的 `tools` 列表中

### 7.2 Adding a Skill

创建 `skills/my-skill/SKILL.md`，包含 YAML front-matter。系统在启动时自动发现。

### 7.3 Adding Loop Middleware

在 `LoopConfig` 中添加字段，并在 `AgentLoop.run()` 的 pre-call 段中调用它。

### 7.4 Changing the System Prompt

编辑 `Agent._build_system()`。每个管理器贡献一个块；按需添加或删除块。

---

## 8. Configuration Reference

### 8.1 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `kimi-k2.5:cloud` | 默认模型名称 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服务 URL |
| `EMAIL_HOST` | — | IMAP/SMTP 服务器地址 |
| `EMAIL_USER` | — | 邮件账户用户名 |
| `EMAIL_PASSWORD` | — | 邮件账户密码（建议通过 keychain 读取） |
| `CALDAV_URL` | — | CalDAV 服务器 URL |

### 8.2 CLI Flags

```
python main.py [options]

  --config FILE        指向 agent.json 配置文件的路径（自动检测 cwd 下的 agent.json）
  --model MODEL        Ollama 模型名称
  --workdir DIR        文档操作根目录
  --workspace DIR      文件操作边界（将所有文件 I/O 限制到此路径）
  --no-todo            禁用内存待办列表
  --no-tasks           禁用持久化任务存储
  --no-email           禁用邮件工具
  --no-calendar        禁用日历工具
  --no-skills          禁用技能包加载
  --no-background      禁用后台任务执行
  --no-subagent        禁用子 Agent 委派
  --no-compact         禁用上下文压缩
```

### 8.3 Runtime Directories

| Path | Purpose |
|---|---|
| `skills/*/SKILL.md` | 技能包定义文件 |
| `.tasks/task_N.json` | 持久化任务文件 |
| `.transcripts/transcript_*.jsonl` | 压缩会话记录 |
| `documents/` | 默认文档工作目录 |

---

## 9. Known Limitations

| # | Issue | Impact |
|---|---|---|
| 1 | Agent 循环无最大迭代次数限制 | 模型可能陷入无限循环 |
| 2 | 邮件发送确认依赖用户响应 | 在无人值守场景下会阻塞执行 |
| 3 | 无额外权限隔离层 | Agent 可代表用户执行任意邮件和日历操作 |
| 4 | 符号链接未校验 | 可能通过符号链接绕过 workspace 限制 |
| 5 | 无自动化测试 | 回归问题无法自动发现 |
| 6 | LLM 调用失败不自动重试 | 单次失败即中止当前轮次 |
| 7 | 邮件和日历凭据以明文环境变量传递 | 存在凭据泄露风险；建议集成系统 keychain |
| 8 | 邮件附件未支持 | `email_read` 只返回正文；无法读取、保存或发送附件 |

---

## 10. Dependencies

```
langchain-ollama    # LangChain Ollama 集成
langchain-core      # 消息与工具抽象
pyyaml              # SKILL.md front-matter 解析
imapclient          # IMAP 邮件读取
smtplib             # SMTP 邮件发送（标准库）
caldav              # CalDAV 日历接口
python-docx         # .docx 文档读写
pymupdf             # .pdf 文档读取
```

**运行时要求：**
- Python 3.10+
- Ollama 服务运行中且可访问
- 已拉取至少一个模型（例如 `ollama pull kimi-k2.5:cloud`）
- 可访问的 IMAP/SMTP 邮件服务器（可选）
- 可访问的 CalDAV 日历服务器（可选）
