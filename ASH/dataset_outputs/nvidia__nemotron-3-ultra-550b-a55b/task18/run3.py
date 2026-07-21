"""
Code Snippet Manager

A secure, self-contained module for managing code snippets with title, description,
language, and tags. Supports saving, searching, editing, deleting, and displaying
snippets with syntax highlighting.

Requires: pygments (pip install pygments)
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from pygments import highlight
    from pygments.formatters import Terminal256Formatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.util import ClassNotFound
except ImportError as e:
    print(f"Error: Required package 'pygments' not found. Install with: pip install pygments", file=sys.stderr)
    raise


# =============================================================================
# Custom Exceptions
# =============================================================================

class SnippetError(Exception):
    """Base exception for snippet manager errors."""
    pass


class SnippetNotFoundError(SnippetError):
    """Raised when a snippet is not found."""
    pass


class ValidationError(SnippetError):
    """Raised when input validation fails."""
    pass


class StorageError(SnippetError):
    """Raised when storage operations fail."""
    pass


# =============================================================================
# Data Models
# =============================================================================

@dataclass(slots=True)
class Snippet:
    """
    Represents a code snippet with metadata.

    Attributes:
        id: Unique identifier (UUID4).
        title: Short title of the snippet.
        description: Longer description of the snippet's purpose.
        language: Programming language (e.g., 'python', 'javascript').
        code: The actual code content.
        tags: List of tags for categorization.
        created_at: ISO format timestamp of creation.
        updated_at: ISO format timestamp of last update.
    """
    id: str
    title: str
    description: str
    language: str
    code: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert snippet to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snippet:
        """Create snippet from dictionary."""
        return cls(**data)


# =============================================================================
# Validation Utilities
# =============================================================================

# Allowed characters for title: alphanumeric, spaces, hyphens, underscores, dots
TITLE_PATTERN = re.compile(r'^[\w\s\-\.]{1,100}$')
# Language pattern: lowercase alphanumeric and hyphens (common language identifiers)
LANGUAGE_PATTERN = re.compile(r'^[a-z0-9\+\#\-]{1,50}$')
# Tag pattern: alphanumeric, hyphens, underscores
TAG_PATTERN = re.compile(r'^[\w\-]{1,30}$')
MAX_DESCRIPTION_LENGTH = 1000
MAX_CODE_LENGTH = 50000
MAX_TAGS = 20


def validate_title(title: str) -> str:
    """
    Validate and sanitize snippet title.

    Args:
        title: The title to validate.

    Returns:
        The validated title.

    Raises:
        ValidationError: If title is invalid.
    """
    if not title or not title.strip():
        raise ValidationError("Title cannot be empty")
    title = title.strip()
    if not TITLE_PATTERN.match(title):
        raise ValidationError(
            "Title must be 1-100 characters and contain only letters, numbers, "
            "spaces, hyphens, underscores, and dots"
        )
    return title


def validate_description(description: str) -> str:
    """
    Validate snippet description.

    Args:
        description: The description to validate.

    Returns:
        The validated description.

    Raises:
        ValidationError: If description is too long.
    """
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(f"Description cannot exceed {MAX_DESCRIPTION_LENGTH} characters")
    return description.strip()


def validate_language(language: str) -> str:
    """
    Validate programming language identifier.

    Args:
        language: The language to validate.

    Returns:
        The validated language (lowercased).

    Raises:
        ValidationError: If language is invalid.
    """
    if not language or not language.strip():
        raise ValidationError("Language cannot be empty")
    language = language.strip().lower()
    if not LANGUAGE_PATTERN.match(language):
        raise ValidationError(
            "Language must be 1-50 characters and contain only lowercase letters, "
            "numbers, hyphens, plus, and hash"
        )
    return language


def validate_tags(tags: list[str]) -> list[str]:
    """
    Validate and sanitize tags.

    Args:
        tags: List of tags to validate.

    Returns:
        List of validated, unique, lowercased tags.

    Raises:
        ValidationError: If any tag is invalid or too many tags provided.
    """
    if len(tags) > MAX_TAGS:
        raise ValidationError(f"Cannot have more than {MAX_TAGS} tags")

    validated = []
    seen = set()
    for tag in tags:
        tag = tag.strip().lower()
        if not tag:
            continue
        if not TAG_PATTERN.match(tag):
            raise ValidationError(
                f"Invalid tag '{tag}': tags must be 1-30 characters and contain only "
                "letters, numbers, hyphens, and underscores"
            )
        if tag not in seen:
            seen.add(tag)
            validated.append(tag)
    return validated


def validate_code(code: str) -> str:
    """
    Validate code content.

    Args:
        code: The code to validate.

    Returns:
        The validated code.

    Raises:
        ValidationError: If code is empty or too long.
    """
    if not code or not code.strip():
        raise ValidationError("Code cannot be empty")
    if len(code) > MAX_CODE_LENGTH:
        raise ValidationError(f"Code cannot exceed {MAX_CODE_LENGTH} characters")
    return code


# =============================================================================
# Storage Layer
# =============================================================================

class SnippetStorage:
    """
    Handles persistent storage of snippets using JSON files.

    Each snippet is stored as a separate JSON file for atomic operations
    and to avoid loading all snippets into memory.
    """

    def __init__(self, storage_dir: str | Path) -> None:
        """
        Initialize storage with a directory path.

        Args:
            storage_dir: Path to directory for storing snippet files.

        Raises:
            StorageError: If directory cannot be created or accessed.
        """
        self._storage_dir = Path(storage_dir).resolve()
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            # Verify write access
            test_file = self._storage_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            raise StorageError(f"Cannot access storage directory '{self._storage_dir}': {e}") from e

    def _snippet_path(self, snippet_id: str) -> Path:
        """
        Get the file path for a snippet ID.

        Args:
            snippet_id: The snippet UUID.

        Returns:
            Path to the snippet JSON file.

        Raises:
            ValidationError: If snippet_id is not a valid UUID format.
        """
        # Validate UUID format to prevent path traversal
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', snippet_id.lower()):
            raise ValidationError("Invalid snippet ID format")
        return self._storage_dir / f"{snippet_id}.json"

    def save(self, snippet: Snippet) -> None:
        """
        Save a snippet to storage.

        Args:
            snippet: The snippet to save.

        Raises:
            StorageError: If save operation fails.
        """
        path = self._snippet_path(snippet.id)
        try:
            # Write atomically using a temporary file
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(snippet.to_dict(), indent=2, ensure_ascii=False))
            temp_path.replace(path)
        except (OSError, json.JSONEncodeError) as e:
            raise StorageError(f"Failed to save snippet {snippet.id}: {e}") from e

    def load(self, snippet_id: str) -> Snippet:
        """
        Load a snippet from storage.

        Args:
            snippet_id: The snippet UUID.

        Returns:
            The loaded snippet.

        Raises:
            SnippetNotFoundError: If snippet does not exist.
            StorageError: If load operation fails.
        """
        path = self._snippet_path(snippet_id)
        if not path.exists():
            raise SnippetNotFoundError(f"Snippet with ID '{snippet_id}' not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Snippet.from_dict(data)
        except (OSError, json.JSONDecodeError) as e:
            raise StorageError(f"Failed to load snippet {snippet_id}: {e}") from e

    def delete(self, snippet_id: str) -> None:
        """
        Delete a snippet from storage.

        Args:
            snippet_id: The snippet UUID.

        Raises:
            SnippetNotFoundError: If snippet does not exist.
            StorageError: If delete operation fails.
        """
        path = self._snippet_path(snippet_id)
        if not path.exists():
            raise SnippetNotFoundError(f"Snippet with ID '{snippet_id}' not found")
        try:
            path.unlink()
        except OSError as e:
            raise StorageError(f"Failed to delete snippet {snippet_id}: {e}") from e

    def list_all(self) -> list[Snippet]:
        """
        List all snippets in storage.

        Returns:
            List of all snippets, sorted by creation date (newest first).

        Raises:
            StorageError: If listing fails.
        """
        snippets = []
        try:
            for path in self._storage_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    snippets.append(Snippet.from_dict(data))
                except (json.JSONDecodeError, TypeError):
                    # Skip corrupted files
                    continue
        except OSError as e:
            raise StorageError(f"Failed to list snippets: {e}") from e

        # Sort by created_at descending (newest first)
        snippets.sort(key=lambda s: s.created_at, reverse=True)
        return snippets

    def search(self, keyword: str | None = None, language: str | None = None, tags: list[str] | None = None) -> list[Snippet]:
        """
        Search snippets by keyword, language, and/or tags.

        Args:
            keyword: Search in title, description, and code (case-insensitive).
            language: Filter by exact language match (case-insensitive).
            tags: Filter by tags (snippet must have ALL specified tags).

        Returns:
            List of matching snippets, sorted by creation date (newest first).

        Raises:
            StorageError: If search fails.
        """
        all_snippets = self.list_all()
        results = []

        keyword_lower = keyword.lower() if keyword else None
        language_lower = language.lower() if language else None
        tags_lower = {t.lower() for t in tags} if tags else None

        for snippet in all_snippets:
            # Keyword search
            if keyword_lower:
                haystack = f"{snippet.title} {snippet.description} {snippet.code}".lower()
                if keyword_lower not in haystack:
                    continue

            # Language filter
            if language_lower and snippet.language.lower() != language_lower:
                continue

            # Tags filter (must have ALL specified tags)
            if tags_lower:
                snippet_tags = {t.lower() for t in snippet.tags}
                if not tags_lower.issubset(snippet_tags):
                    continue

            results.append(snippet)

        return results


# =============================================================================
# Syntax Highlighting
# =============================================================================

def highlight_code(code: str, language: str) -> str:
    """
    Apply syntax highlighting to code using Pygments.

    Args:
        code: The code to highlight.
        language: The programming language identifier.

    Returns:
        ANSI-colored code string for terminal display.

    Raises:
        ValidationError: If language is not supported by Pygments.
    """
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except ClassNotFound:
        # Try to guess the lexer from the code
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            raise ValidationError(f"Unsupported language: '{language}'")

    formatter = Terminal256Formatter(style="monokai")
    return highlight(code, lexer, formatter)


# =============================================================================
# Snippet Manager (High-level API)
# =============================================================================

class SnippetManager:
    """
    High-level manager for code snippets.

    Provides a clean API for creating, reading, updating, deleting,
    searching, and displaying snippets with proper validation and error handling.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        """
        Initialize the snippet manager.

        Args:
            storage_dir: Directory for snippet storage. Defaults to
                         ~/.local/share/snippet_manager/ or ./snippets/
        """
        if storage_dir is None:
            # Follow XDG Base Directory Specification
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            storage_dir = base / "snippet_manager"
        self._storage = SnippetStorage(storage_dir)

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------

    def create(
        self,
        title: str,
        code: str,
        language: str,
        description: str = "",
        tags: list[str] | None = None
    ) -> Snippet:
        """
        Create a new snippet.

        Args:
            title: Short title (1-100 chars, alphanumeric + space, -, _, .)
            code: The code content (non-empty, max 50000 chars)
            language: Programming language identifier
            description: Optional description (max 1000 chars)
            tags: Optional list of tags (max 20, each 1-30 chars alphanumeric + -, _)

        Returns:
            The created snippet with generated ID and timestamps.

        Raises:
            ValidationError: If any input is invalid.
            StorageError: If save operation fails.
        """
        # Validate all inputs
        title = validate_title(title)
        code = validate_code(code)
        language = validate_language(language)
        description = validate_description(description)
        tags = validate_tags(tags or [])

        # Create snippet
        snippet = Snippet(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            language=language,
            code=code,
            tags=tags,
        )

        self._storage.save(snippet)
        return snippet

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    def get(self, snippet_id: str) -> Snippet:
        """
        Retrieve a snippet by ID.

        Args:
            snippet_id: The snippet UUID.

        Returns:
            The snippet.

        Raises:
            SnippetNotFoundError: If snippet does not exist.
            ValidationError: If snippet_id format is invalid.
            StorageError: If load operation fails.
        """
        return self._storage.load(snippet_id)

    def list_all(self) -> list[Snippet]:
        """
        List all snippets.

        Returns:
            List of all snippets, newest first.

        Raises:
            StorageError: If listing fails.
        """
        return self._storage.list_all()

    def search(
        self,
        keyword: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None
    ) -> list[Snippet]:
        """
        Search snippets.

        Args:
            keyword: Search in title, description, and code (case-insensitive).
            language: Filter by exact language match (case-insensitive).
            tags: Filter by tags (snippet must have ALL specified tags).

        Returns:
            List of matching snippets, newest first.

        Raises:
            StorageError: If search fails.
        """
        return self._storage.search(keyword=keyword, language=language, tags=tags)

    # -------------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------------

    def update(
        self,
        snippet_id: str,
        title: str | None = None,
        code: str | None = None,
        language: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None
    ) -> Snippet:
        """
        Update an existing snippet.

        Args:
            snippet_id