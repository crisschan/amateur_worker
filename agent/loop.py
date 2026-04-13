from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.messages import HumanMessage, ToolMessage


@dataclass
class LoopConfig:
    compact_manager: Optional[Any] = None   # CompactManager | None
    bg_manager: Optional[Any] = None        # BackgroundManager | None
    todo_manager: Optional[Any] = None      # TodoManager | None
    todo_nag_interval: int = 3


class AgentLoop:
    """Stateless agent loop: runs one full turn (LLM ↔ tool calls) to completion."""

    def __init__(self, llm, tools: list, loop_config: LoopConfig):
        self._llm = llm
        self._tool_map = {t.name: t for t in tools}
        self._cfg = loop_config

    def run(self, messages: list) -> None:
        """Execute the loop until the model stops requesting tools.

        *messages* is mutated in-place — new AI and tool messages are appended.
        """
        while True:
            # ── Pre-call middleware ──────────────────────────────────────────
            self._drain_bg_notifications(messages)
            self._inject_todo_nag(messages)
            self._run_compaction(messages)

            if self._cfg.todo_manager:
                self._cfg.todo_manager.tick()

            # ── LLM call ────────────────────────────────────────────────────
            ai_msg = self._llm.invoke(messages)
            messages.append(ai_msg)

            # ── Check for tool calls ─────────────────────────────────────────
            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                break  # model is done

            # ── Execute each tool ────────────────────────────────────────────
            for call in tool_calls:
                tool_name = call["name"]
                tool_args = call["args"]
                call_id = call["id"]

                t = self._tool_map.get(tool_name)
                if t is None:
                    result = f"Error: unknown tool '{tool_name}'"
                else:
                    try:
                        result = t.invoke(tool_args)
                    except Exception as exc:
                        result = f"Error: {exc}"

                # Track todo calls
                if tool_name == "todo" and self._cfg.todo_manager:
                    pass  # tick handled above; todo_manager already updated internally

                messages.append(
                    ToolMessage(content=str(result), tool_call_id=call_id)
                )

    # ── Middleware helpers ────────────────────────────────────────────────────

    def _drain_bg_notifications(self, messages: list) -> None:
        bg = self._cfg.bg_manager
        if bg is None:
            return
        notes = bg.drain_notifications()
        for note in notes:
            messages.append(HumanMessage(content=note))

    def _inject_todo_nag(self, messages: list) -> None:
        tm = self._cfg.todo_manager
        if tm is None:
            return
        if tm.nag_due():
            messages.append(HumanMessage(content=tm.nag_message()))

    def _run_compaction(self, messages: list) -> None:
        cm = self._cfg.compact_manager
        if cm is None:
            return
        cm.micro_compact(messages)
        cm.maybe_auto_compact(messages)
