"""code_snippet_manager.py

A simple, file‑based code snippet manager.

Features
--------
* Store snippets with title, description, language, tags and source code.
* Search snippets by keyword, language or tags.
* Edit and delete existing snippets.
* Render snippets with syntax highlighting using Pygments.

The manager persists data in a JSON file located at the path supplied to
`SnippetManager`.  All public functions are type‑annotated and contain
docstrings.  Errors are reported through custom exception classes.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third‑party dependency – widely used for syntax highlighting
try:
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.util import ClassNotFound
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Pygments is required for syntax highlighting. Install it via "
        "`pip install pygments`."
    ) from exc


class SnippetError(Exception):
    """Base class for snippet‑related errors."""


class SnippetNotFoundError(SnippetError):
    """Raised when a snippet cannot be found by its identifier."""


class DuplicateTitleError(SnippetError):
    """Raised when attempting to add a snippet with a title that already exists."""


def _validate_non_empty_string(value: str, field_name: str) -> None:
    """Validate that a string is non‑empty and does not contain control characters."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non‑empty string.")
    if re.search(r"[\x00-\x1F\x7F]", value):
        raise ValueError(f"{field_name} contains prohibited control characters.")


def _validate_tags(tags: List[str]) -> None:
    """Validate that tags are a list of non‑empty strings."""
    if not isinstance(tags, list):
        raise TypeError("tags must be a list of strings.")
    for tag in tags:
        _validate_non_empty_string(tag, "tag")


@dataclass
class Snippet:
    """Data container for a code snippet."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    language: str = ""
    tags: List[str] = field(default_factory=list)
    code: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def update_timestamp(self) -> None:
        """Refresh the `updated_at` timestamp to the current UTC time."""
        self.updated_at = datetime.utcnow().isoformat()


class SnippetManager:
    """Manage a collection of snippets persisted to a JSON file."""

    def __init__(self, storage_path: Path) -> None:
        """
        Initialise the manager.

        Parameters
        ----------
        storage_path: Path
            File path where snippets are stored. The file is created if it does not exist.
        """
        self.storage_path = storage_path.expanduser().resolve()
        self._snippets: Dict[str, Snippet] = {}
        self._load()

    def _load(self) -> None:
        """Load snippets from the JSON storage file."""
        if not self.storage_path.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text("[]", encoding="utf-8")
        try:
            raw_data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for item in raw_data:
                snippet = Snippet(**item)
                self._snippets[snippet.id] = snippet
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SnippetError(f"Failed to load snippets: {exc}") from exc

    def _save(self) -> None:
        """Write the current snippet collection to the JSON storage file."""
        try:
            data = [asdict(snippet) for snippet in self._snippets.values()]
            self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            raise SnippetError(f"Failed to write snippets to disk: {exc}") from exc

    def add_snippet(
        self,
        title: str,
        description: str,
        language: str,
        tags: List[str],
        code: str,
    ) -> str:
        """
        Add a new snippet.

        Returns
        -------
        str
            Identifier of the newly created snippet.

        Raises
        ------
        DuplicateTitleError
            If another snippet already uses the same title.
        ValueError
            If any of the provided fields are invalid.
        """
        _validate_non_empty_string(title, "title")
        _validate_non_empty_string(description, "description")
        _validate_non_empty_string(language, "language")
        _validate_tags(tags)
        _validate_non_empty_string(code, "code")

        if any(s.title == title for s in self._snippets.values()):
            raise DuplicateTitleError(f"A snippet with title '{title}' already exists.")

        snippet = Snippet(
            title=title,
            description=description,
            language=language,
            tags=tags,
            code=code,
        )
        self._snippets[snippet.id] = snippet
        self._save()
        return snippet.id

    def get_snippet(self, snippet_id: str) -> Snippet:
        """
        Retrieve a snippet by its identifier.

        Raises
        ------
        SnippetNotFoundError
            If no snippet matches the supplied identifier.
        """
        snippet = self._snippets.get(snippet_id)
        if snippet is None:
            raise SnippetNotFoundError(f"Snippet with id '{snippet_id}' not found.")
        return snippet

    def edit_snippet(
        self,
        snippet_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        code: Optional[str] = None,
    ) -> None:
        """
        Edit mutable fields of a snippet.

        Only the supplied keyword arguments are updated.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        DuplicateTitleError
            If the new title collides with another snippet's title.
        ValueError
            If provided values are invalid.
        """
        snippet = self.get_snippet(snippet_id)

        if title is not None:
            _validate_non_empty_string(title, "title")
            if any(s.title == title and s.id != snippet_id for s in self._snippets.values()):
                raise DuplicateTitleError(f"A snippet with title '{title}' already exists.")
            snippet.title = title

        if description is not None:
            _validate_non_empty_string(description, "description")
            snippet.description = description

        if language is not None:
            _validate_non_empty_string(language, "language")
            snippet.language = language

        if tags is not None:
            _validate_tags(tags)
            snippet.tags = tags

        if code is not None:
            _validate_non_empty_string(code, "code")
            snippet.code = code

        snippet.update_timestamp()
        self._save()

    def delete_snippet(self, snippet_id: str) -> None:
        """
        Remove a snippet from the collection.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        """
        if snippet_id not in self._snippets:
            raise SnippetNotFoundError(f"Snippet with id '{snippet_id}' not found.")
        del self._snippets[snippet_id]
        self._save()

    def search_snippets(
        self,
        keyword: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Snippet]:
        """
        Search snippets by keyword (in title/description), language, or tags.

        Parameters
        ----------
        keyword: Optional[str]
            Text to search for in title and description (case‑insensitive).
        language: Optional[str]
            Programming language to filter by (case‑insensitive exact match).
        tags: Optional[List[str]]
            List of tags; a snippet matches if it contains **all** supplied tags.

        Returns
        -------
        List[Snippet]
            Matching snippets; empty list if none match.
        """
        results = list(self._snippets.values())

        if keyword:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            results = [
                s
                for s in results
                if pattern.search(s.title) or pattern.search(s.description)
            ]

        if language:
            lang_lower = language.lower()
            results = [s for s in results if s.language.lower() == lang_lower]

        if tags:
            tag_set = {t.lower() for t in tags}
            results = [
                s for s in results if tag_set.issubset({t.lower() for t in s.tags})
            ]

        return results

    def display_snippet(self, snippet_id: str, style: str = "friendly") -> str:
        """
        Return HTML with syntax‑highlighted code for the given snippet.

        Parameters
        ----------
        snippet_id: str
            Identifier of the snippet to render.
        style: str, optional
            Pygments style name (default: "friendly").

        Returns
        -------
        str
            HTML fragment containing highlighted code.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        SnippetError
            If the language lexer cannot be found.
        """
        snippet = self.get_snippet(snippet_id)

        try:
            lexer = get_lexer_by_name(snippet.language.lower())
        except ClassNotFound:
            # Fall back to lexer guessing; if that fails, raise a clear error.
            try:
                lexer = guess_lexer(snippet.code)
            except ClassNotFound as exc:
                raise SnippetError(
                    f"Unable to determine lexer for language '{snippet.language}'."
                ) from exc

        formatter = HtmlFormatter(style=style, full=False, linenos=False)
        highlighted = highlight(snippet.code, lexer, formatter)
        return highlighted

    def list_all(self) -> List[Snippet]:
        """
        Return a list of all stored snippets, sorted by creation date descending.

        Returns
        -------
        List[Snippet]
        """
        return sorted(
            self._snippets.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )