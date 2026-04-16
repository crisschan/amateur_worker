#!/usr/bin/env python3
"""Office Agent — entry point.

Usage:
    python main.py [options]

Run `python main.py --help` for full option list.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="office-agent",
        description="Interactive AI office assistant powered by a local Ollama LLM.",
    )
    p.add_argument("--config", metavar="FILE", help="Path to agent.json config file (auto-detected if cwd contains agent.json)")
    p.add_argument("--model", metavar="MODEL", help="Ollama model name")
    p.add_argument("--workdir", metavar="DIR", help="Document root directory")
    p.add_argument("--workspace", metavar="DIR", help="File I/O boundary (restricts all reads/writes)")
    p.add_argument("--query", metavar="TEXT", help="Run a single query instead of starting the REPL")

    # Feature toggle flags
    p.add_argument("--no-todo", action="store_true", help="Disable in-memory todo list")
    p.add_argument("--no-tasks", action="store_true", help="Disable persistent task storage")
    p.add_argument("--no-email", action="store_true", help="Disable email tools")
    p.add_argument("--no-calendar", action="store_true", help="Disable calendar tools")
    p.add_argument("--no-skills", action="store_true", help="Disable skill loader")
    p.add_argument("--no-background", action="store_true", help="Disable background task execution")
    p.add_argument("--no-subagent", action="store_true", help="Disable sub-agent delegation")
    p.add_argument("--no-compact", action="store_true", help="Disable context compaction")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    from agent.config import AgentConfig, ConfigError

    # Auto-detect agent.json in cwd, handle permission issues gracefully
    cfg = AgentConfig()
    try:
        if args.config:
            config_path = Path(args.config)
            if config_path.exists():
                cfg = AgentConfig.from_file(config_path)
        else:
            try:
                config_path = Path.cwd() / "agent.json"
                if config_path.exists():
                    cfg = AgentConfig.from_file(config_path)
            except Exception:
                # Skip auto config detection if cwd not accessible
                pass
    except ConfigError as exc:
        print(f"Error loading config: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Apply CLI overrides ───────────────────────────────────────────────────
    if args.model:
        cfg.model = args.model
    if args.workdir:
        cfg.workdir = Path(args.workdir).resolve()
    if args.workspace:
        cfg.workspace = Path(args.workspace).resolve()

    if args.no_todo:
        cfg.enable_todo = False
    if args.no_tasks:
        cfg.enable_tasks = False
    if args.no_email:
        cfg.enable_email = False
    if args.no_calendar:
        cfg.enable_calendar = False
    if args.no_skills:
        cfg.enable_skills = False
    if args.no_background:
        cfg.enable_background = False
    if args.no_subagent:
        cfg.enable_subagent = False
    if args.no_compact:
        cfg.enable_compact = False

    # ── Build agent ───────────────────────────────────────────────────────────
    from agent.agent import Agent
    agent = Agent(cfg)

    # ── Run ───────────────────────────────────────────────────────────────────
    if args.query:
        result = agent.run_query(args.query)
        print(result)
    else:
        agent.repl()


if __name__ == "__main__":
    main()
