from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig

FRONTMATTER_SEP = "---"


def _parse_skill_file(path: Path) -> dict:
    """Parse a SKILL.md file and return metadata + body."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    meta: dict = {}
    body_start = 0

    if lines and lines[0].strip() == FRONTMATTER_SEP:
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == FRONTMATTER_SEP), None)
        if end is not None:
            fm_text = "\n".join(lines[1:end])
            try:
                meta = yaml.safe_load(fm_text) or {}
            except Exception:
                pass
            body_start = end + 1

    meta["_body"] = "\n".join(lines[body_start:])
    meta["_path"] = str(path)
    return meta


def _scan_skills(skills_dir: Path) -> dict[str, dict]:
    """Return {skill-name: metadata} for all discovered SKILL.md files."""
    skills: dict[str, dict] = {}
    if not skills_dir.exists():
        return skills
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        try:
            info = _parse_skill_file(skill_md)
            name = info.get("name") or skill_md.parent.name
            skills[name] = info
        except Exception:
            pass
    return skills


class SkillLoader:
    def __init__(self, config: "AgentConfig"):
        self._config = config
        self._skills: dict[str, dict] = _scan_skills(config.skills_dir)

    def skill_summaries(self) -> str:
        """Return a multi-line string of skill names + one-line descriptions."""
        if not self._skills:
            return "(no skills loaded)"
        lines = []
        for name, info in self._skills.items():
            desc = info.get("description", "no description")
            lines.append(f"  {name}: {desc}")
        return "\n".join(lines)

    def create_tools(self) -> list:
        loader = self

        @tool
        def load_skill(name: str) -> str:
            """Load the full instructions for a skill by name.

            Args:
                name: The skill name as listed in the system prompt.
            """
            info = loader._skills.get(name)
            if info is None:
                available = ", ".join(loader._skills.keys()) or "(none)"
                return f"Skill '{name}' not found. Available: {available}"
            return info.get("_body", "(empty skill body)")

        return [load_skill]
