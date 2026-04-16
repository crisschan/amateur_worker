from __future__ import annotations

import sys
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from agent.config import AgentConfig
from agent.loop import AgentLoop, LoopConfig
from agent.memory.compact import CompactManager
from agent.tools.documents import create_document_tools
from agent.tools.skills import SkillLoader


class Agent:
    def __init__(self, config: Optional[AgentConfig] = None):
        self._config = config or AgentConfig()
        self._messages: list = []
        self._build()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        cfg = self._config

        # 1. LLM client
        self._llm_raw = ChatOllama(
            model=cfg.model,
            base_url=cfg.base_url,
            temperature=cfg.temperature,
            num_predict=cfg.max_tokens,
        )

        # 2. Always-on: document tools
        tools = create_document_tools(cfg)

        # 3. Optional managers
        self._todo_manager = None
        self._task_tools: list = []
        self._bg_manager = None
        self._compact_manager = None
        self._skill_loader: Optional[SkillLoader] = None

        if cfg.enable_todo:
            from agent.tools.todo import TodoManager
            self._todo_manager = TodoManager(cfg)
            tools += self._todo_manager.create_tools()

        if cfg.enable_tasks:
            from agent.tools.tasks import create_task_tools
            tools += create_task_tools(cfg)

        
        
        if cfg.enable_skills:
            self._skill_loader = SkillLoader(cfg)
            tools += self._skill_loader.create_tools()

        if cfg.enable_background:
            from agent.tools.background import BackgroundManager
            self._bg_manager = BackgroundManager(cfg)
            tools += self._bg_manager.create_tools()

        if cfg.enable_compact:
            self._compact_manager = CompactManager(cfg, self._llm_raw)
            # compact tool (layer 3 — model-initiated)
            from langchain_core.tools import tool

            compact_mgr = self._compact_manager

            @tool
            def compact(focus: str = "") -> str:
                """Request context compaction before the next LLM call.

                Use this when the conversation history is very long and you want to
                summarise it to free up context space.

                Args:
                    focus: Optional hint about what to preserve in the summary.
                """
                return compact_mgr.request_compact()

            tools.append(compact)

        if cfg.enable_subagent:
            llm_for_sub = self._llm_raw
            from agent.tools.subagent import create_subagent_tools
            tools += create_subagent_tools(cfg, llm_for_sub)

        # 4. Bind tools
        self._llm = self._llm_raw.bind_tools(tools)
        self._tools = tools

        # 5. Loop
        loop_cfg = LoopConfig(
            compact_manager=self._compact_manager,
            bg_manager=self._bg_manager,
            todo_manager=self._todo_manager,
            todo_nag_interval=cfg.todo_nag_interval,
        )
        self._loop = AgentLoop(self._llm, tools, loop_cfg)

        # 6. System prompt
        system = self._build_system()
        self._messages = [SystemMessage(content=system)]

    def _build_system(self) -> str:
        cfg = self._config
        parts = [
            "You are an interactive AI office assistant running locally.",
            "Execute tasks directly using the available tools. Do not just explain — act.",
            f"Working directory: {cfg.workdir}",
            f"Workspace boundary: {cfg.effective_workspace}",
        ]

        if cfg.enable_todo:
            parts.append(
                "\n## Todo List\nUse the `todo` tool to maintain a running list of tasks. "
                "Keep it current — update statuses as you work."
            )

        if cfg.enable_tasks:
            parts.append(
                "\n## Persistent Tasks\nUse task_create / task_update / task_list / task_get "
                "for long-lived tasks that should survive session restarts."
            )

        
        
        if cfg.enable_skills and self._skill_loader:
            summaries = self._skill_loader.skill_summaries()
            parts.append(
                f"\n## Skills\nAvailable skills (use load_skill to get full instructions):\n{summaries}\n\n"
                "### Skill Workflow\n"
                "When you cannot complete a task with current capabilities:\n"
                "1. Use search_skill to find existing skills online\n"
                "2. If found, use install_skill to add it\n"
                "3. If not found, use create_skill to build a new one\n"
                "4. Use load_skill to get full instructions for any skill"
            )

        if cfg.enable_background:
            parts.append(
                "\n## Background Tasks\nUse background_run for long operations "
                "Check status with check_background."
            )

        if cfg.enable_subagent:
            parts.append(
                "\n## Sub-agents\nDelegate self-contained document tasks with the `task` tool. "
                "Sub-agents can read/write documents but cannot send email or modify calendars."
            )

        if cfg.enable_compact:
            parts.append(
                "\n## Context Management\nCall `compact` if the conversation history grows very long "
                "and you need to free up context space."
            )

        return "\n".join(parts)

    # ── Public API ────────────────────────────────────────────────────────────

    def repl(self) -> None:
        """Start an interactive REPL session."""
        print(f"Office Agent ready (model: {self._config.model}). Type 'exit' or Ctrl-C to quit.\n")
        while True:
            try:
                user_input = input(f"\033[36m Amateur >> \033[0m")
                user_input = user_input.strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye.")
                break

            self._messages.append(HumanMessage(content=user_input))
            try:
                self._loop.run(self._messages)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print(f"\n[Error: {exc}]\n")
                continue

            # Print last AI message，当出现错误时，AIMessage.content 可能为空字符串，展示 tool_calls 的调用情况作为兜底
            # for msg in reversed(self._messages):
            #     if isinstance(msg, AIMessage):
            #         print(f"\nAssistant> {msg.content}\n")
            #         break
            for msg in reversed(self._messages):
                if isinstance(msg, AIMessage):
                    if msg.content:
                        print(f"\nAssistant> {msg.content}\n")
                    elif msg.tool_calls:
                        # 至少告知用户模型在做什么
                        names = [tc["name"] for tc in msg.tool_calls]
                        print(f"\nAssistant> [正在调用工具: {', '.join(names)}]\n")
                    else:
                        print("\nAssistant> [无响应内容]\n")
                    break
            else:
                print("\nAssistant> [未收到模型响应]\n")

    def run_query(self, query: str) -> str:
        """Run a single query and return the model's response (stateless)."""
        messages = [self._messages[0], HumanMessage(content=query)]  # keep system prompt
        self._loop.run(messages)
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return msg.content or ""
        return ""
