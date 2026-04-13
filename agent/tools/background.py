from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig

ALLOWED_OPS = {"email_batch_send", "email_export", "doc_export", "calendar_sync"}
TIMEOUT_SECONDS = 300


class _BackgroundTask:
    def __init__(self, task_id: str, op_type: str, params: dict):
        self.task_id = task_id
        self.op_type = op_type
        self.params = params
        self.status: str = "running"  # running | completed | error | timeout
        self.result: str = ""
        self.started_at = time.time()


def _run_op(task: _BackgroundTask, notify_queue: queue.Queue, config: "AgentConfig") -> None:
    """Execute the background operation and post a notification."""
    try:
        result = _dispatch(task.op_type, task.params, config)
        task.status = "completed"
        task.result = result
    except Exception as exc:
        task.status = "error"
        task.result = str(exc)
    finally:
        elapsed = time.time() - task.started_at
        if elapsed >= TIMEOUT_SECONDS:
            task.status = "timeout"
            task.result = f"Error: Timeout ({TIMEOUT_SECONDS}s)"
        notify_queue.put({
            "task_id": task.task_id,
            "op_type": task.op_type,
            "status": task.status,
            "result": task.result[:500],
        })


def _dispatch(op_type: str, params: dict, config: "AgentConfig") -> str:
    """Route op_type to the appropriate handler."""
    if op_type == "email_batch_send":
        return _email_batch_send(params, config)
    elif op_type == "email_export":
        return _email_export(params, config)
    elif op_type == "doc_export":
        return _doc_export(params, config)
    elif op_type == "calendar_sync":
        return _calendar_sync(params, config)
    else:
        raise ValueError(f"Unknown op_type: {op_type}")


def _email_batch_send(params: dict, config: "AgentConfig") -> str:
    from agent.tools.email import _smtp_connect
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    emails = params.get("emails", [])
    if not emails:
        return "No emails to send."
    S = _smtp_connect(config)
    sent = 0
    for item in emails:
        msg = MIMEMultipart()
        msg["From"] = config.email_user
        msg["To"] = item["to"]
        msg["Subject"] = item["subject"]
        msg.attach(MIMEText(item["body"], "plain", "utf-8"))
        S.sendmail(config.email_user, [item["to"]], msg.as_string())
        sent += 1
    S.quit()
    return f"Batch sent {sent} emails."


def _email_export(params: dict, config: "AgentConfig") -> str:
    import email as email_lib
    from agent.tools.email import _imap_connect, _get_text_body, _decode_header
    from pathlib import Path
    folder = params.get("folder", "INBOX")
    start = params.get("start", "")
    end = params.get("end", "")
    dest_path = params.get("dest_path", "email_export.txt")
    M = _imap_connect(config)
    M.select(folder)
    criteria = "ALL"
    if start:
        criteria = f'SINCE "{start}"'
    _, data = M.search(None, criteria)
    ids = data[0].split()
    lines = []
    for uid in ids:
        _, msg_data = M.fetch(uid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw)
        body = _get_text_body(msg)
        lines.append(f"--- From:{_decode_header(msg.get('From',''))} Subject:{_decode_header(msg.get('Subject',''))} ---\n{body}\n")
    M.logout()
    safe = (config.effective_workspace / dest_path).resolve()
    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.write_text("\n".join(lines), encoding="utf-8")
    return f"Exported {len(ids)} emails to {dest_path}."


def _doc_export(params: dict, config: "AgentConfig") -> str:
    from pathlib import Path
    src_path = params.get("src_path", "")
    fmt = params.get("format", "txt")
    src = (config.effective_workspace / src_path).resolve()
    if not src.exists():
        return f"Source file not found: {src_path}"
    dest = src.with_suffix(f".{fmt}")
    if fmt == "txt":
        text = src.read_text(encoding="utf-8", errors="replace")
        dest.write_text(text, encoding="utf-8")
    else:
        return f"Unsupported export format: {fmt}"
    return f"Exported {src_path} → {dest.name}."


def _calendar_sync(params: dict, config: "AgentConfig") -> str:
    from agent.tools.calendar import _get_caldav_calendar
    cal = _get_caldav_calendar(config)
    cal.sync()
    return "Calendar synced."


class BackgroundManager:
    def __init__(self, config: "AgentConfig"):
        self._config = config
        self._tasks: Dict[str, _BackgroundTask] = {}
        self._notify_queue: queue.Queue = queue.Queue()

    def drain_notifications(self) -> list[str]:
        """Return all pending completion notifications and clear the queue."""
        messages = []
        while True:
            try:
                note = self._notify_queue.get_nowait()
                messages.append(
                    f"[Background task {note['task_id']} ({note['op_type']}) {note['status']}]: {note['result']}"
                )
            except queue.Empty:
                break
        return messages

    def create_tools(self) -> list:
        manager = self

        @tool
        def background_run(op_type: str, params: dict) -> str:
            """Start a background office operation and return a task ID immediately.

            Allowed op_types: email_batch_send, email_export, doc_export, calendar_sync.

            Args:
                op_type: The type of background operation.
                params: Parameters for the operation (varies by op_type).
            """
            if op_type not in ALLOWED_OPS:
                return f"Error: op_type '{op_type}' is not allowed. Allowed: {sorted(ALLOWED_OPS)}"
            task_id = str(uuid.uuid4())[:8]
            task = _BackgroundTask(task_id, op_type, params)
            manager._tasks[task_id] = task
            t = threading.Thread(
                target=_run_op,
                args=(task, manager._notify_queue, manager._config),
                daemon=True,
            )
            t.start()
            return f"Background task started: {task_id} (op: {op_type})"

        @tool
        def check_background(task_id: Optional[str] = None) -> str:
            """Check the status of background tasks.

            Args:
                task_id: Specific task ID to check, or None to list all tasks.
            """
            import json
            if task_id is not None:
                t = manager._tasks.get(task_id)
                if t is None:
                    return f"Task '{task_id}' not found."
                return json.dumps({
                    "task_id": t.task_id,
                    "op_type": t.op_type,
                    "status": t.status,
                    "result": t.result[:200],
                })
            if not manager._tasks:
                return "No background tasks."
            return json.dumps([
                {"task_id": t.task_id, "op_type": t.op_type, "status": t.status}
                for t in manager._tasks.values()
            ], indent=2)

        return [background_run, check_background]
