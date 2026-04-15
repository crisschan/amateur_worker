from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class ConfigError(Exception):
    pass


@dataclass
class AgentConfig:
    # LLM
    model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "kimi-k2.5:cloud"))
    base_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    temperature: float = 0.2
    max_tokens: int = 4096

    # Paths
    workdir: Path = field(default_factory=lambda: Path(os.path.abspath('.')))
    workspace: Optional[Path] = None

    # Context management
    context_threshold: int = 50000
    keep_recent_tools: int = 3
    todo_nag_interval: int = 3

    # Feature flags
    enable_todo: bool = True
    enable_tasks: bool = True
    enable_email: bool = True
    enable_calendar: bool = True
    enable_skills: bool = True
    enable_skill_search: bool = True
    enable_background: bool = True
    enable_subagent: bool = True
    enable_compact: bool = True
    
    # Skill repository
    skill_repository_url: str = field(default_factory=lambda: os.environ.get("SKILL_REPOSITORY", "https://clawhub.ai"))

    # Email
    email_host: Optional[str] = field(default_factory=lambda: os.environ.get("EMAIL_HOST"))
    email_port_imap: int = field(default_factory=lambda: int(os.environ.get("EMAIL_PORT_IMAP", "993")))
    email_port_smtp: int = field(default_factory=lambda: int(os.environ.get("EMAIL_PORT_SMTP", "587")))
    email_user: Optional[str] = field(default_factory=lambda: os.environ.get("EMAIL_USER"))
    email_password: Optional[str] = field(default_factory=lambda: os.environ.get("EMAIL_PASSWORD"))

    # Calendar
    caldav_url: Optional[str] = field(default_factory=lambda: os.environ.get("CALDAV_URL"))

    # --- Derived paths (read-only properties) ---

    @property
    def effective_workspace(self) -> Path:
        return self.workspace if self.workspace is not None else self.workdir

    @property
    def skills_dir(self) -> Path:
        return self.workdir / "skills"

    @property
    def tasks_dir(self) -> Path:
        return self.workdir / ".tasks"

    @property
    def transcripts_dir(self) -> Path:
        return self.workdir / ".transcripts"

    # --- Loader ---

    @classmethod
    def from_file(cls, path: str | Path) -> "AgentConfig":
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        with open(path) as f:
            data = json.load(f)

        base_dir = path.parent
        cfg = cls()

        # Resolve path fields relative to config file location
        path_fields = {"workdir", "workspace"}
        for key, value in data.items():
            if not hasattr(cfg, key):
                continue  # silently ignore unknown keys
            if key in path_fields and value is not None:
                setattr(cfg, key, (base_dir / value).resolve())
            else:
                setattr(cfg, key, value)

        return cfg
