from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from agent.config import AgentConfig

MAX_READ_BYTES = 50 * 1024  # 50 KB


def _make_safe_path(raw: str, workspace: Path) -> Path:
    """Resolve *raw* relative to *workspace* and verify it stays inside it."""
    p = (workspace / raw).resolve()
    try:
        p.relative_to(workspace.resolve())
    except ValueError:
        raise ValueError(f"Path '{raw}' is outside the workspace boundary '{workspace}'")
    return p


def _read_text(path: Path, limit: Optional[int]) -> str:
    ext = path.suffix.lower()
    if ext == ".docx":
        try:
            import docx  # python-docx
            doc = docx.Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as exc:
            raise RuntimeError(f"Cannot read .docx: {exc}") from exc
    elif ext == ".pdf":
        try:
            import fitz  # pymupdf
            doc = fitz.open(str(path))
            text = "\n".join(page.get_text() for page in doc)
        except Exception as exc:
            raise RuntimeError(f"Cannot read .pdf: {exc}") from exc
    else:
        text = path.read_text(encoding="utf-8", errors="replace")

    if limit is not None:
        text = text[:limit]
    return text[:MAX_READ_BYTES]


def create_document_tools(config: "AgentConfig") -> list:
    workspace = config.effective_workspace

    @tool
    def read_document(path: str, limit: Optional[int] = None) -> str:
        """Read the contents of a document file.

        Supports .txt, .md, .docx, and .pdf files.
        Output is capped at 50 KB. Supply *limit* (characters) for a smaller slice.

        Args:
            path: Path to the file, relative to the workspace root.
            limit: Optional character limit.
        """
        safe = _make_safe_path(path, workspace)
        if not safe.exists():
            return f"Error: File not found: {path}"
        if not safe.is_file():
            return f"Error: Not a file: {path}"
        try:
            return _read_text(safe, limit)
        except Exception as exc:
            return f"Error reading file: {exc}"

    @tool
    def write_document(path: str, content: str) -> str:
        """Write content to a document file, creating parent directories as needed.

        Args:
            path: Destination path relative to the workspace root.
            content: Text content to write.
        """
        safe = _make_safe_path(path, workspace)
        try:
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return f"Written: {path} ({len(content)} chars)"
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error writing file: {exc}"

    @tool
    def edit_document(path: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of *old_text* with *new_text* in a file.

        Args:
            path: Path relative to the workspace root.
            old_text: Exact text to find and replace.
            new_text: Replacement text.
        """
        safe = _make_safe_path(path, workspace)
        if not safe.exists():
            return f"Error: File not found: {path}"
        try:
            original = safe.read_text(encoding="utf-8")
            if old_text not in original:
                return "Error: old_text not found in the file."
            updated = original.replace(old_text, new_text, 1)
            safe.write_text(updated, encoding="utf-8")
            return f"Edited: {path}"
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error editing file: {exc}"

    @tool
    def list_documents(path: str = ".") -> str:
        """List document files in a directory with last-modified timestamps.

        Args:
            path: Directory path relative to the workspace root (default: workspace root).
        """
        safe = _make_safe_path(path, workspace)
        if not safe.exists():
            return f"Error: Directory not found: {path}"
        if not safe.is_dir():
            return f"Error: Not a directory: {path}"
        doc_exts = {".txt", ".md", ".docx", ".pdf", ".rst", ".csv"}
        lines = []
        for entry in sorted(safe.iterdir()):
            if entry.is_file() and entry.suffix.lower() in doc_exts:
                mtime = entry.stat().st_mtime
                from datetime import datetime
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                lines.append(f"{entry.name}  ({mtime_str})")
        if not lines:
            return f"No document files found in: {path}"
        return "\n".join(lines)

    return [read_document, write_document, edit_document, list_documents]
