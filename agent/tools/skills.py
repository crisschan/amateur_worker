from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
import requests
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

        @tool
        def search_skill(query: str) -> str:
            """Search online skill repository for available skills.

            Use this when you cannot complete a user's task with current capabilities.
            Searches multiple sources including GitHub, skill repositories, and documentation.

            Args:
                query: Search keywords describing the required capability
            """
            if not loader._config.enable_skill_search:
                return "Skill search is disabled in configuration"

            try:
                # Try primary skill repository first
                try:
                    resp = requests.get(
                        f"{loader._config.skill_repository_url}/api/search",
                        params={"q": query},
                        timeout=10
                    )
                    resp.raise_for_status()
                    results = resp.json()

                    if results:
                        lines = ["Found available skills in repository:"]
                        for skill in results:
                            lines.append(f"- {skill['name']}: {skill['description']}")
                            lines.append(f"  Install URL: {skill['install_url']}")
                            lines.append("")
                        return "\n".join(lines)
                except Exception:
                    pass

                # Fallback: search GitHub for skill implementations
                try:
                    gh_resp = requests.get(
                        "https://api.github.com/search/repositories",
                        params={
                            "q": f"{query} skill in:name,description language:python",
                            "sort": "stars",
                            "order": "desc",
                            "per_page": 5
                        },
                        timeout=10,
                        headers={"Accept": "application/vnd.github.v3+json"}
                    )
                    gh_resp.raise_for_status()
                    gh_results = gh_resp.json().get("items", [])

                    if gh_results:
                        lines = ["Found potential skill implementations on GitHub:"]
                        for repo in gh_results:
                            lines.append(f"- {repo['name']}: {repo['description'] or 'No description'}")
                            lines.append(f"  Repository: {repo['html_url']}")
                            lines.append(f"  Stars: {repo['stargazers_count']}")
                            lines.append("")
                        return "\n".join(lines)
                except Exception:
                    pass

                return f"No matching skills found for '{query}'. Consider creating a new skill using the skill-creator tool."

            except Exception as e:
                return f"Skill search failed: {str(e)}"

        @tool
        def install_skill(url: str, confirm: bool = False) -> str:
            """Install a skill from repository URL.
            
            Args:
                url: Skill install URL from search results
                confirm: Set to True to confirm installation after review
            """
            if not loader._config.enable_skill_search:
                return "Skill installation is disabled in configuration"
                
            if not confirm:
                return f"{{\"status\": \"pending_confirmation\", \"url\": \"{url}\"}}"
                
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                    tmp.write(resp.content)
                    tmp_path = Path(tmp.name)
                
                skills_dir = loader._config.skills_dir
                skills_dir.mkdir(exist_ok=True)
                
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    zf.extractall(skills_dir)
                
                tmp_path.unlink()
                
                # Rescan skills after install
                loader._skills = _scan_skills(loader._config.skills_dir)
                
                return "Skill installed successfully and is now available"
            except Exception as e:
                return f"Skill installation failed: {str(e)}"

        @tool
        def create_skill(name: str, description: str, instructions: str) -> str:
            """Create a new skill locally when no existing skill matches the requirement.

            Args:
                name: Skill name (lowercase, hyphen-separated)
                description: One-line description of what the skill does
                instructions: Full skill instructions and implementation details
            """
            try:
                skills_dir = loader._config.skills_dir
                skill_dir = skills_dir / name
                skill_dir.mkdir(parents=True, exist_ok=True)

                # Create SKILL.md with frontmatter
                skill_md = skill_dir / "SKILL.md"
                content = f"""---
name: {name}
description: {description}
type: custom
created: {__import__('datetime').datetime.now().isoformat()}
---

{instructions}
"""
                skill_md.write_text(content, encoding="utf-8")

                # Rescan skills after creation
                loader._skills = _scan_skills(loader._config.skills_dir)

                return f"Skill '{name}' created successfully at {skill_dir}"
            except Exception as e:
                return f"Failed to create skill: {str(e)}"

        @tool
        def run_skill(name: str, code: str) -> str:
            """Execute Python code extracted from a skill's instructions.

            Use this after load_skill to actually run the skill's code and return
            real output. Do NOT write a standalone script file — call this instead.

            Args:
                name: The skill name (for logging only).
                code: Complete, self-contained Python code to execute.
            """
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["python3", tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout.strip()
                error = result.stderr.strip()
                if result.returncode != 0:
                    return f"[skill:{name}] 执行出错:\n{error}" + (f"\n{output}" if output else "")
                return output or f"[skill:{name}] 执行完成（无输出）"
            except subprocess.TimeoutExpired:
                return f"[skill:{name}] 执行超时（30s）"
            except Exception as exc:
                return f"[skill:{name}] 执行失败: {exc}"
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return [load_skill, run_skill, search_skill, install_skill, create_skill]
