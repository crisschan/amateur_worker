from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig

_TODO_ITEMS: list[dict] = []
_LAST_CALLED_ROUND: int = -1
_CURRENT_ROUND: int = 0

Status = str  # "pending" | "in_progress" | "completed"


class TodoManager:
    MAX_ITEMS = 20

    def __init__(self, config: "AgentConfig"):
        self._config = config
        self._items: list[dict] = []
        self._last_called_round: int = -1
        self._current_round: int = 0

    def tick(self) -> None:
        self._current_round += 1

    def nag_due(self) -> bool:
        rounds_since = self._current_round - self._last_called_round
        return rounds_since > self._config.todo_nag_interval

    def nag_message(self) -> str:
        return (
            "Reminder: please update your todo list to reflect current task status "
            f"(it has been {self._current_round - self._last_called_round} rounds since the last update)."
        )

    def create_tools(self) -> list:
        manager = self

        @tool
        def todo(items: List[dict]) -> str:
            """Replace the entire in-memory todo list with the supplied items.

            Each item must have 'id' (str), 'text' (str), and
            'status' ("pending" | "in_progress" | "completed").
            Only one item may be in_progress at a time. Max 20 items.

            Args:
                items: New full list of todo items.
            """
            if len(items) > manager.MAX_ITEMS:
                return f"Error: Too many items (max {manager.MAX_ITEMS})."
            in_progress = [i for i in items if i.get("status") == "in_progress"]
            if len(in_progress) > 1:
                return "Error: Only one item may be in_progress at a time."
            for item in items:
                if "id" not in item:
                    item["id"] = str(uuid.uuid4())[:8]
                if item.get("status") not in ("pending", "in_progress", "completed"):
                    item["status"] = "pending"
            manager._items = items
            manager._last_called_round = manager._current_round
            summary = "\n".join(f"[{i['status']}] {i['id']}: {i['text']}" for i in items)
            return f"Todo list updated ({len(items)} items):\n{summary}"

        return [todo]

    def get_items(self) -> list[dict]:
        return list(self._items)
