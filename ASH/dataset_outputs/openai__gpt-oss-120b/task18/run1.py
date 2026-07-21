"""
code_snippet_manager.py

A simple, file‑based code snippet manager supporting creation, retrieval,
search, editing, deletion, and terminal syntax highlighting.

Features
--------
* Store snippets with title, description, language, tags, and source code.
* Persistent storage in a JSON file (default: ``snippets.json`` in the user's
  config directory).
* Search by keyword (title, description, tags, code) or by programming
  language.
* Edit and delete snippets safely.
* Display snippets with syntax highlighting using Pygments.

Security considerations
------------------------
* All file I/O is confined to the dedicated storage directory.
* Input data is validated and sanitized where appropriate.
* Exceptions are caught and transformed into domain‑specific errors.
"""

from __future__ import annotations

import json
import uuid
import datetime
import pathlib
import sys
import threading
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Iterable

# Third‑party dependency – widely used and pure Python
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import TerminalFormatter
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Pygments is required for syntax highlighting. Install it via "
        "`pip install pygments`."
    ) from exc


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class SnippetError(Exception):
    """Base class for all snippet manager errors."""


class SnippetNotFoundError(SnippetError):
    """Raised when a snippet with a given identifier cannot be found."""


class SnippetStorageError(SnippetError):
    """Raised for I/O or serialization problems."""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class Snippet:
    """Represent a single code snippet."""

    id: str
    title: str
    description: str
    language: str
    tags: List[str]
    code: str
    created_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    @staticmethod
    def from_dict(data: Dict[str, object]) -> "Snippet":
        """Create a Snippet instance from a raw dictionary."""
        required = {"id", "title", "description", "language", "tags", "code", "created_at", "updated_at"}
        missing = required - data.keys()
        if missing:
            raise SnippetStorageError(f"Missing fields in snippet data: {missing}")
        return Snippet(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data["description"]),
            language=str(data["language"]),
            tags=list(map(str, data["tags"])),
            code=str(data["code"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialise the snippet to a plain dictionary."""
        return asdict(self)


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #

class SnippetManager:
    """
    Manage a collection of Snippet objects persisted to a JSON file.

    The manager is thread‑safe for concurrent read/write operations.
    """

    def __init__(self, storage_path: Optional[pathlib.Path] = None) -> None:
        """
        Initialise the manager.

        Parameters
        ----------
        storage_path:
            Path to the JSON file used for persistence. If omitted,
            ``~/.config/snippet_manager/snippets.json`` is used.
        """
        self._lock = threading.RLock()
        self.storage_path = storage_path or pathlib.Path.home() / ".config" / "snippet_manager" / "snippets.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._snippets: Dict[str, Snippet] = {}
        self._load()

    # ------------------------------------------------------------------- #
    # Persistence helpers
    # ------------------------------------------------------------------- #

    def _load(self) -> None:
        """Load snippets from the JSON storage file."""
        with self._lock:
            if not self.storage_path.is_file():
                self._snippets = {}
                return
            try:
                raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self._snippets = {
                    str(item["id"]): Snippet.from_dict(item) for item in raw
                }
            except (json.JSONDecodeError, OSError) as exc:
                raise SnippetStorageError(f"Failed to read storage file: {exc}") from exc

    def _save(self) -> None:
        """Write the current snippet collection to the JSON storage file."""
        with self._lock:
            try:
                serialisable = [snip.to_dict() for snip in self._snippets.values()]
                self.storage_path.write_text(json.dumps(serialisable, indent=2, sort_keys=True), encoding="utf-8")
            except OSError as exc:
                raise SnippetStorageError(f"Failed to write storage file: {exc}") from exc

    # ------------------------------------------------------------------- #
    # CRUD operations
    # ------------------------------------------------------------------- #

    def add_snippet(
        self,
        title: str,
        description: str,
        language: str,
        tags: Iterable[str],
        code: str,
    ) -> Snippet:
        """
        Create and store a new snippet.

        Parameters
        ----------
        title:
            Human‑readable title.
        description:
            Detailed description.
        language:
            Programming language identifier (e.g., ``python``, ``javascript``).
        tags:
            Iterable of tag strings.
        code:
            The source code.

        Returns
        -------
        Snippet:
            The newly created snippet instance.
        """
        if not title.strip():
            raise ValueError("Title must not be empty.")
        if not language.strip():
            raise ValueError("Language must not be empty.")
        snippet_id = str(uuid.uuid4())
        snippet = Snippet(
            id=snippet_id,
            title=title.strip(),
            description=description.strip(),
            language=language.strip().lower(),
            tags=[t.strip().lower() for t in tags if t.strip()],
            code=code,
        )
        with self._lock:
            self._snippets[snippet_id] = snippet
            self._save()
        return snippet

    def get_snippet(self, snippet_id: str) -> Snippet:
        """
        Retrieve a snippet by its identifier.

        Parameters
        ----------
        snippet_id:
            UUID string of the snippet.

        Returns
        -------
        Snippet:
            The requested snippet.

        Raises
        ------
        SnippetNotFoundError:
            If no snippet matches the given identifier.
        """
        with self._lock:
            try:
                return self._snippets[snippet_id]
            except KeyError as exc:
                raise SnippetNotFoundError(f"Snippet {snippet_id} not found.") from exc

    def edit_snippet(
        self,
        snippet_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        code: Optional[str] = None,
    ) -> Snippet:
        """
        Update fields of an existing snippet.

        Parameters
        ----------
        snippet_id:
            Identifier of the snippet to edit.
        title, description, language, tags, code:
            Optional new values. ``None`` leaves the field unchanged.

        Returns
        -------
        Snippet:
            The updated snippet.

        Raises
        ------
        SnippetNotFoundError:
            If the snippet does not exist.
        """
        with self._lock:
            snippet = self.get_snippet(snippet_id)
            if title is not None:
                if not title.strip():
                    raise ValueError("Title must not be empty.")
                snippet.title = title.strip()
            if description is not None:
                snippet.description = description.strip()
            if language is not None:
                if not language.strip():
                    raise ValueError("Language must not be empty.")
                snippet.language = language.strip().lower()
            if tags is not None:
                snippet.tags = [t.strip().lower() for t in tags if t.strip()]
            if code is not None:
                snippet.code = code
            snippet.updated_at = datetime.datetime.utcnow().isoformat()
            self._snippets[snippet_id] = snippet
            self._save()
            return snippet

    def delete_snippet(self, snippet_id: str) -> None:
        """
        Remove a snippet from storage.

        Parameters
        ----------
        snippet_id:
            Identifier of the snippet to delete.

        Raises
        ------
        SnippetNotFoundError:
            If the snippet does not exist.
        """
        with self._lock:
            if snippet_id not in self._snippets:
                raise SnippetNotFoundError(f"Snippet {snippet_id} not found.")
            del self._snippets[snippet_id]
            self._save()

    # ------------------------------------------------------------------- #
    # Query utilities
    # ------------------------------------------------------------------- #

    def search(
        self,
        keyword: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Snippet]:
        """
        Search snippets by keyword and/or language.

        Parameters
        ----------
        keyword:
            Case‑insensitive substring to look for in title, description,
            tags, or code.
        language:
            Exact language match (case‑insensitive).

        Returns
        -------
        List[Snippet]:
            All snippets satisfying the criteria.
        """
        keyword_lc = (keyword or "").lower()
        language_lc = (language or "").lower()
        results: List[Snippet] = []

        with self._lock:
            for snip in self._snippets.values():
                if language_lc and snip.language != language_lc:
                    continue
                if keyword_lc:
                    in_fields = (
                        keyword_lc in snip.title.lower()
                        or keyword_lc in snip.description.lower()
                        or any(keyword_lc in tag for tag in snip.tags)
                        or keyword_lc in snip.code.lower()
                    )
                    if not in_fields:
                        continue
                results.append(snip)
        return results

    def list_snippets(self) -> List[Snippet]:
        """
        Return all stored snippets sorted by creation date.

        Returns
        -------
        List[Snippet]:
            All snippets.
        """
        with self._lock:
            return sorted(
                self._snippets.values(),
                key=lambda s: s.created_at,
            )

    # ------------------------------------------------------------------- #
    # Display helpers
    # ------------------------------------------------------------------- #

    def display_snippet(self, snippet_id: str, stream: Optional[object] = None) -> None:
        """
        Print a snippet with syntax highlighting to the given stream.

        Parameters
        ----------
        snippet_id:
            Identifier of the snippet to display.
        stream:
            Text stream to write to. Defaults to ``sys.stdout``.
        """
        stream = stream or sys.stdout
        snippet = self.get_snippet(snippet_id)

        # Header
        header = (
            f"Title      : {snippet.title}\n"
            f"Description: {snippet.description}\n"
            f"Language   : {snippet.language}\n"
            f"Tags       : {', '.join(snippet.tags)}\n"
            f"Created    : {snippet.created_at}\n"
            f"Updated    : {snippet.updated_at}\n"
            f"{'-' * 40}\n"
        )
        print(header, file=stream)

        # Syntax highlighted code
        lexer = self._choose_lexer(snippet.language, snippet.code)
        highlighted = highlight(snippet.code, lexer, TerminalFormatter())
        print(highlighted, file=stream)

    @staticmethod
    def _choose_lexer(language: str, code: str):
        """
        Resolve a Pygments lexer for the given language, falling back to guessing.

        Parameters
        ----------
        language:
            Language identifier supplied by the user.
        code:
            Source code (used as fallback for guessing).

        Returns
        -------
        Lexer:
            Pygments lexer instance.
        """
        try:
            return get_lexer_by_name(language)
        except Exception:
            # If the explicit name fails, let Pygments guess.
            try:
                return guess_lexer(code)
            except Exception:
                # Fallback to plain text lexer.
                from pygments.lexers import TextLexer
                return TextLexer()


__all__ = [
    "Snippet",
    "SnippetManager",
    "SnippetError",
    "SnippetNotFoundError",
    "SnippetStorageError",
]