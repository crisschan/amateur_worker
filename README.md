# Office Agent - 本地 AI 办公助手

> 一个基于本地 Ollama LLM 的交互式 CLI 办公助手，具备文档管理、邮件收发、日历调度、任务追踪和后台处理能力。

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/ollama-powered-orange.svg)](https://ollama.com/)

---

## ✨ 功能特性

| 模块 | 功能描述 |
|------|---------|
| 📄 **文档管理** | 读取/写入/编辑文档，支持 TXT/MD/DOCX/PDF 格式，路径安全隔离 |
| 📧 **邮件管理** | IMAP/SMTP 邮件收发，两阶段确认发送，搜索与回复 |
| 📅 **日历管理** | CalDAV 日程管理，事件创建/更新/删除，空闲时段查找 |
| 📋 **任务管理** | 持久化任务存储，依赖图管理 |
| ⚙️ **后台执行** | 守护线程异步执行耗时操作，不阻塞交互 |
| 🧠 **子 Agent** | 子任务委派，上下文隔离并行处理 |
| 📦 **技能系统** | 按需加载办公场景技能包 |
| 🗜️ **上下文压缩** | 三层压缩策略，防止会话溢出 |

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Ollama 服务运行中
- 已拉取至少一个 LLM 模型（如 `kimi-k2.5:cloud` 或 `qwen2.5`）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd amateur_worker

# 安装依赖
pip install -r requirements.txt
```

### 运行

```bash
# 交互式 REPL 模式
python main.py

# 单次查询模式
python main.py --query "帮我整理今天的会议记录"

# 指定配置文件
python main.py --config agent.json
```

---

## ⚙️ 配置

### 配置文件 `agent.json`


- workdir主要用于：定义代理程序的工作根目录；构建系统目录路径（skills/、.tasks/、.transcripts/；作为workspace的默认值

- workspace主要用于：文档操作的安全边界；所有文件操作的安全性验证；防止路径遍历攻击

- 关键区别：workdir是系统级配置，影响整个代理程序的运行环境；workspace是文件操作的安全边界，保护文件系统安全；当workspace为None时，使用workdir作为默认工作空间。

```json
{
  "model": "qwen2.5",
  "base_url": "http://localhost:11434",
  "workdir": ".",
  "workspace": ".",
  "temperature": 0.2,
  
  "enable_todo": true,
  "enable_tasks": true,
  "enable_email": true,
  "enable_calendar": true,
  "enable_skills": true,
  "enable_background": true,
  "enable_subagent": true,
  "enable_compact": true
}
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `OLLAMA_MODEL` | 默认 Ollama 模型名称 |
| `OLLAMA_BASE_URL` | Ollama 服务地址 |

```
export EMAIL_HOST=imap.yourprovider.com
export EMAIL_USER=you@example.com
export EMAIL_PASSWORD=yourpassword
export CALDAV_URL=https://your-caldav-server/
```

### CLI 参数

```
--config FILE        配置文件路径
--model MODEL        Ollama 模型名称
--workdir DIR        文档工作目录
--workspace DIR      文件操作边界
--query TEXT         运行单次查询

--no-todo            禁用待办列表
--no-tasks           禁用任务存储
--no-email           禁用邮件工具
--no-calendar        禁用日历工具
--no-skills          禁用技能系统
--no-background      禁用后台执行
--no-subagent        禁用子 Agent
--no-compact         禁用上下文压缩
```

---

## 🛠️ 可用工具

### 文档工具
- `read_document(path)` - 读取文档
- `write_document(path, content)` - 写入文档
- `edit_document(path, old_text, new_text)` - 编辑文档
- `list_documents(path)` - 列出文档

### 邮件工具
- `email_list()` - 列出邮件
- `email_read(email_id)` - 读取邮件
- `email_send(to, subject, body)` - 发送邮件（两阶段确认）
- `email_reply(email_id, body)` - 回复邮件
- `email_search(query)` - 搜索邮件

### 日历工具
- `calendar_list(start, end)` - 列出日程
- `calendar_get(event_id)` - 获取事件详情
- `calendar_create(title, start, end)` - 创建事件
- `calendar_update(event_id, ...)` - 更新事件
- `calendar_delete(event_id)` - 删除事件
- `calendar_find_slot(duration, attendees)` - 查找空闲时段

### 任务与后台
- `task_create(subject, description, due_date)` - 创建任务
- `task_list()` - 列出任务
- `background_run(op_type, params)` - 后台执行任务
- `task(prompt, description)` - 委派子 Agent

---

## 📦 内置技能包

项目内置常用办公场景技能：

| 技能 | 描述 |
|------|------|
| 📧 `email-templates` | 常用邮件模板（请假、会议邀请、周报等） |
| 📝 `meeting-minutes` | 会议纪要生成格式规范 |
| 📊 `report-formatting` | 报告排版与结构指引 |
| 📅 `calendar-etiquette` | 日程安排最佳实践 |

---

## 🏗️ 架构设计

```
main.py
  └─ Agent
       ├─ AgentConfig
       ├─ AgentLoop
       ├─ Tools (文档/邮件/日历/待办/任务/后台/技能/子Agent)
       └─ Memory (上下文压缩管理器)
```

### 请求生命周期

```
用户输入 → 消息历史 → AgentLoop
  ├─ 预处理：后台通知 / 待办提醒 / 上下文压缩
  ├─ LLM 调用
  ├─ 工具调用执行（循环直到不再调用工具）
  └─ 返回最终响应给用户
```

---

## 🔒 安全设计

1. **路径隔离**：所有文件操作限制在 `workspace` 范围内，防止路径遍历
2. **两阶段确认**：邮件发送与日历删除需要用户明确确认
3. **子 Agent 隔离**：子 Agent 仅拥有文档权限，无法访问邮件/日历
4. **无自动重试**：错误返回给 LLM 由其决策处理方式

---

## 📁 目录结构

```
amateur_worker/
├── main.py              # 程序入口
├── agent.json           # 配置文件
├── requirements.txt     # 依赖列表
├── agent/
│   ├── agent.py         # Agent 主类
│   ├── config.py        # 配置定义
│   ├── loop.py          # Agent 循环
│   ├── tools/           # 各工具模块
│   └── memory/          # 内存管理
├── skills/              # 技能包目录
│   └── */SKILL.md       # 各技能定义
├── documents/           # 默认文档目录
├── .tasks/              # 持久化任务存储
└── .transcripts/        # 会话历史归档
```

---

## ⚠️ 已知限制

1. Agent 循环无最大迭代次数限制，模型可能陷入无限循环
2. 邮件附件尚未支持
3. 无自动化测试覆盖
4. 凭据目前通过环境变量传递，建议后续集成系统钥匙串
5. 符号链接未进行安全校验

---

## 📄 许可证

MIT License

---

> 本项目是本地优先的办公助手设计，所有操作均在您的计算机上本地执行，不依赖云服务。