from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

if TYPE_CHECKING:
    from agent.config import AgentConfig

PLACEHOLDER = "[tool result truncated]"


def estimate_tokens(messages: list) -> int:
    return len(str(messages)) // 4


class CompactManager:
    def __init__(self, config: "AgentConfig", llm: Any):
        self._config = config
        self._llm = llm
        self._compact_flag = False

    def request_compact(self) -> str:
        """Called by the compact tool — sets the flag so compaction runs before next LLM call."""
        self._compact_flag = True
        return "Compaction scheduled before the next LLM call."

    # ------------------------------------------------------------------
    # Layer 1 — micro-compact (silent, every round)
    # ------------------------------------------------------------------

    def micro_compact(self, messages: list) -> None:
        """Replace old ToolMessage content with a placeholder in-place.

        The most recent `keep_recent_tools` ToolMessages are left intact.
        """
        from langchain_core.messages import ToolMessage

        tool_indices = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage)]
        cutoff = len(tool_indices) - self._config.keep_recent_tools
        for idx in tool_indices[:cutoff]:
            msg = messages[idx]
            if msg.content != PLACEHOLDER:
                messages[idx] = ToolMessage(
                    content=PLACEHOLDER,
                    tool_call_id=msg.tool_call_id,
                )

    # ------------------------------------------------------------------
    # Layer 2 — auto-compact (threshold-triggered)
    # ------------------------------------------------------------------

    def maybe_auto_compact(self, messages: list) -> None:
        """Run full compaction if context is too large or the compact flag is set."""
        should_compact = self._compact_flag or (
            self._config.enable_compact
            and estimate_tokens(messages) > self._config.context_threshold
        )
        if should_compact:
            self._compact_flag = False
            self._run_full_compact(messages)

    def _run_full_compact(self, messages: list) -> None:
        """Save transcript, generate summary, replace messages in-place."""
        self._save_transcript(messages)

        # Build a condensed version of the conversation for summarisation
        summary_prompt = self._build_summary_prompt(messages)
        try:
            response = self._llm.invoke([HumanMessage(content=summary_prompt)])
            summary_text = response.content
        except Exception as exc:  # noqa: BLE001
            summary_text = f"[Summary unavailable: {exc}]"

        # Replace message list in-place
        messages.clear()
        messages.append(HumanMessage(content=f"[Session summary]\n{summary_text}"))
        messages.append(AIMessage(content="Understood. I have the session summary and am ready to continue."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_transcript(self, messages: list) -> None:
        self._config.transcripts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._config.transcripts_dir / f"transcript_{ts}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for msg in messages:
                record = {
                    "type": type(msg).__name__,
                    "content": msg.content if hasattr(msg, "content") else str(msg),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _build_summary_prompt(messages: list) -> str:
        lines = ["Below is a conversation history. Please write a concise continuity summary (max 400 words) that captures:"]
        lines.append("- Key facts and decisions established so far")
        lines.append("- Outstanding tasks or pending actions")
        lines.append("- Any important user preferences or constraints mentioned\n")
        lines.append("Conversation history:\n")
        for msg in messages:
            role = type(msg).__name__.replace("Message", "")
            content = msg.content if hasattr(msg, "content") else str(msg)
            lines.append(f"[{role}]: {content[:500]}")
        return "\n".join(lines)
