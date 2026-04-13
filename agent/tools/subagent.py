from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig


def create_subagent_tools(config: "AgentConfig", llm) -> list:

    @tool
    def task(prompt: str, description: str = "") -> str:
        """Delegate an independent sub-task to a child agent and return its final answer.

        The child agent has access only to document tools and skills — it cannot send
        email, modify the calendar, create tasks, or spawn further sub-agents.

        Args:
            prompt: The task instruction for the sub-agent.
            description: Optional brief description for logging purposes.
        """
        # Import here to avoid circular dependency at module load time
        from agent.config import AgentConfig
        from agent.tools.documents import create_document_tools
        from agent.tools.skills import SkillLoader
        from agent.loop import AgentLoop, LoopConfig

        # Build isolated config for sub-agent (no email/calendar/tasks/todo/background/subagent/compact)
        sub_config = AgentConfig(
            model=config.model,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            workdir=config.workdir,
            workspace=config.workspace,
            enable_email=False,
            enable_calendar=False,
            enable_todo=False,
            enable_tasks=False,
            enable_background=False,
            enable_subagent=False,
            enable_skills=config.enable_skills,
            enable_compact=False,  # sub-agent does not compact on its own
        )

        # Build tool list: documents + skills only
        sub_tools = create_document_tools(sub_config)
        if sub_config.enable_skills:
            loader = SkillLoader(sub_config)
            sub_tools += loader.create_tools()

        # Bind tools to a fresh LLM instance
        sub_llm = llm.bind_tools(sub_tools)

        # Build a minimal system prompt
        system_prompt = (
            "You are a focused sub-agent. Complete the assigned task using only document tools. "
            "Do not attempt to send email, modify calendars, or delegate further. "
            "Return a clear, complete answer when done."
        )

        from langchain_core.messages import SystemMessage
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        loop = AgentLoop(sub_llm, sub_tools, LoopConfig())
        try:
            loop.run(messages)
            # Return the last AI message content
            from langchain_core.messages import AIMessage
            for msg in reversed(messages):
                if isinstance(msg, AIMessage):
                    return msg.content or "(sub-agent returned empty response)"
            return "(sub-agent produced no output)"
        except Exception as exc:
            return f"Sub-agent error: {exc}"

    return [task]
