from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig


def _task_path(tasks_dir: Path, task_id: int) -> Path:
    return tasks_dir / f"task_{task_id}.json"


def _load_task(tasks_dir: Path, task_id: int) -> dict | None:
    p = _task_path(tasks_dir, task_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_task(tasks_dir: Path, task: dict) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    p = _task_path(tasks_dir, task["id"])
    p.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")


def _next_id(tasks_dir: Path) -> int:
    existing = [int(p.stem.split("_")[1]) for p in tasks_dir.glob("task_*.json") if p.stem.split("_")[1].isdigit()]
    return max(existing, default=0) + 1


def _all_tasks(tasks_dir: Path) -> list[dict]:
    tasks = []
    for p in sorted(tasks_dir.glob("task_*.json")):
        try:
            tasks.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return tasks


def create_task_tools(config: "AgentConfig") -> list:
    tasks_dir = config.tasks_dir

    @tool
    def task_create(subject: str, description: str, due_date: Optional[str] = None) -> str:
        """Create a new persistent task.

        Args:
            subject: Short title for the task.
            description: Detailed description of what needs to be done.
            due_date: Optional due date in YYYY-MM-DD format.
        """
        task_id = _next_id(tasks_dir)
        task = {
            "id": task_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
            "due_date": due_date or "",
        }
        _save_task(tasks_dir, task)
        return f"Task #{task_id} created: {subject}"

    @tool
    def task_update(
        task_id: int,
        status: Optional[str] = None,
        add_blocked_by: Optional[List[int]] = None,
        add_blocks: Optional[List[int]] = None,
        owner: Optional[str] = None,
    ) -> str:
        """Update a task's status, dependencies, or owner.

        When a task is completed it is automatically removed from other tasks' blockedBy lists.

        Args:
            task_id: The ID of the task to update.
            status: New status: "pending", "in_progress", or "completed".
            add_blocked_by: List of task IDs that must complete before this task.
            add_blocks: List of task IDs that this task blocks.
            owner: Assign the task to an owner (free-form string).
        """
        task = _load_task(tasks_dir, task_id)
        if task is None:
            return f"Error: Task #{task_id} not found."

        if status is not None:
            valid = {"pending", "in_progress", "completed"}
            if status not in valid:
                return f"Error: invalid status '{status}'. Must be one of {valid}."
            task["status"] = status

        if add_blocked_by:
            for dep_id in add_blocked_by:
                if dep_id not in task["blockedBy"]:
                    task["blockedBy"].append(dep_id)
                # Update reverse link
                dep = _load_task(tasks_dir, dep_id)
                if dep is not None:
                    if task_id not in dep["blocks"]:
                        dep["blocks"].append(task_id)
                    _save_task(tasks_dir, dep)

        if add_blocks:
            for blocked_id in add_blocks:
                if blocked_id not in task["blocks"]:
                    task["blocks"].append(blocked_id)
                # Update reverse link
                blocked = _load_task(tasks_dir, blocked_id)
                if blocked is not None:
                    if task_id not in blocked["blockedBy"]:
                        blocked["blockedBy"].append(task_id)
                    _save_task(tasks_dir, blocked)

        if owner is not None:
            task["owner"] = owner

        # If completed, remove from other tasks' blockedBy lists
        if task.get("status") == "completed":
            for other in _all_tasks(tasks_dir):
                if other["id"] == task_id:
                    continue
                if task_id in other.get("blockedBy", []):
                    other["blockedBy"].remove(task_id)
                    _save_task(tasks_dir, other)

        _save_task(tasks_dir, task)
        return f"Task #{task_id} updated."

    @tool
    def task_list() -> str:
        """List all tasks with their ID, subject, status, and blocked-by info."""
        tasks_dir.mkdir(parents=True, exist_ok=True)
        tasks = _all_tasks(tasks_dir)
        if not tasks:
            return "No tasks found."
        lines = []
        for t in tasks:
            blocked = f" [blocked by: {t['blockedBy']}]" if t.get("blockedBy") else ""
            owner = f" (@{t['owner']})" if t.get("owner") else ""
            due = f" due:{t['due_date']}" if t.get("due_date") else ""
            lines.append(f"#{t['id']} [{t['status']}]{owner}{due} {t['subject']}{blocked}")
        return "\n".join(lines)

    @tool
    def task_get(task_id: int) -> str:
        """Get the full details of a single task.

        Args:
            task_id: The task ID.
        """
        task = _load_task(tasks_dir, task_id)
        if task is None:
            return f"Error: Task #{task_id} not found."
        return json.dumps(task, indent=2, ensure_ascii=False)

    return [task_create, task_update, task_list, task_get]
