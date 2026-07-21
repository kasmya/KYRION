"""
Code Snippet Manager

A module for managing code snippets with title, description, language, and tags.
Supports saving, searching, editing, deleting, and displaying snippets with syntax highlighting.

Features:
- Persistent storage using JSON
- Search by keyword, language, or tags
- Syntax highlighting via Pygments (falls back to plain text if unavailable)
- Comprehensive error handling and input validation
- Type hints and full documentation

Example usage:
    manager = SnippetManager("snippets.json")
    snippet_id = manager.add_snippet(
        title="Hello World",
        description="Simple Python example",
        language="python",
        tags=["example", "beginner"],
        code='print("Hello, World!")'
    )
    snippets = manager.search_snippets(keyword="hello")
    manager.display_snippet(snippet_id)
"""

import json
import uuid
import datetime
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer, ClassNotFound
    from pygments.formatters import TerminalFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


class SnippetManagerError(Exception):
    """Base exception for SnippetManager errors."""
    pass


class SnippetNotFoundError(SnippetManagerError):
    """Raised when a snippet with the given ID is not found."""
    pass


class ValidationError(SnippetManagerError):
    """Raised when input validation fails."""
    pass


class StorageError(SnippetManagerError):
    """Raised when storage operations fail."""
    pass


class SnippetManager:
    """
    Manages a collection of code snippets with persistent JSON storage.

    Attributes:
        storage_path: Path to the JSON file used for persistence.
    """

    def __init__(self, storage_path: Union[str, Path]) -> None:
        """
        Initialize the SnippetManager with a storage file.

        Args:
            storage_path: Path to the JSON storage file.

        Raises:
            StorageError: If the storage file cannot be read or initialized.
        """
        self.storage_path = Path(storage_path)
        self._snippets: List[Dict[str, Any]] = []
        self._load_storage()

    def _load_storage(self) -> None:
        """Load snippets from the storage file."""
        if not self.storage_path.exists():
            self._snippets = []
            return

        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise StorageError("Storage file does not contain a valid snippet list")
            self._snippets = data
        except json.JSONDecodeError as e:
            raise StorageError(f"Invalid JSON in storage file: {e}") from e
        except OSError as e:
            raise StorageError(f"Cannot read storage file: {e}") from e

    def _save_storage(self) -> None:
        """Save snippets to the storage file."""
        try:
            # Ensure parent directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self.storage_path.open("w", encoding="utf-8") as f:
                json.dump(self._snippets, f, indent=2, ensure_ascii=False)
        except OSError as e:
            raise StorageError(f"Cannot write to storage file: {e}") from e

    def _validate_snippet_data(
        self,
        title: str,
        description: str,
        language: str,
        tags: List[str],
        code: str
    ) -> None:
        """
        Validate snippet data before saving.

        Args:
            title: Snippet title.
            description: Snippet description.
            language: Programming language.
            tags: List of tags.
            code: Source code.

        Raises:
            ValidationError: If any field is invalid.
        """
        if not title or not title.strip():
            raise ValidationError("Title cannot be empty")
        if not isinstance(description, str):
            raise ValidationError("Description must be a string")
        if not language or not language.strip():
            raise ValidationError("Language cannot be empty")
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValidationError("Tags must be a list of strings")
        if not code or not isinstance(code, str):
            raise ValidationError("Code cannot be empty")

    def _generate_timestamp(self) -> str:
        """Generate an ISO format timestamp."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def add_snippet(
        self,
        title: str,
        description: str,
        language: str,
        tags: List[str],
        code: str
    ) -> str:
        """
        Add a new snippet to the collection.

        Args:
            title: Short title for the snippet.
            description: Detailed description.
            language: Programming language (e.g., "python", "javascript").
            tags: List of tags for categorization.
            code: Source code content.

        Returns:
            The unique ID of the created snippet.

        Raises:
            ValidationError: If input validation fails.
            StorageError: If saving to storage fails.
        """
        self._validate_snippet_data(title, description, language, tags, code)

        snippet_id = str(uuid.uuid4())
        timestamp = self._generate_timestamp()

        snippet = {
            "id": snippet_id,
            "title": title.strip(),
            "description": description.strip(),
            "language": language.strip().lower(),
            "tags": [tag.strip().lower() for tag in tags if tag.strip()],
            "code": code,
            "created_at": timestamp,
            "updated_at": timestamp
        }

        self._snippets.append(snippet)
        self._save_storage()
        return snippet_id

    def get_snippet(self, snippet_id: str) -> Dict[str, Any]:
        """
        Retrieve a snippet by its ID.

        Args:
            snippet_id: Unique identifier of the snippet.

        Returns:
            The snippet dictionary.

        Raises:
            SnippetNotFoundError: If no snippet with the given ID exists.
        """
        for snippet in self._snippets:
            if snippet["id"] == snippet_id:
                return snippet
        raise SnippetNotFoundError(f"Snippet with ID '{snippet_id}' not found")

    def update_snippet(
        self,
        snippet_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        code: Optional[str] = None
    ) -> bool:
        """
        Update an existing snippet.

        Args:
            snippet_id: Unique identifier of the snippet to update.
            title: New title (optional).
            description: New description (optional).
            language: New language (optional).
            tags: New tags list (optional).
            code: New code content (optional).

        Returns:
            True if the snippet was updated.

        Raises:
            SnippetNotFoundError: If the snippet does not exist.
            ValidationError: If provided fields are invalid.
            StorageError: If saving fails.
        """
        snippet = self.get_snippet(snippet_id)  # Raises if not found

        # Validate only provided fields
        if title is not None:
            if not title or not title.strip():
                raise ValidationError("Title cannot be empty")
            snippet["title"] = title.strip()

        if description is not None:
            if not isinstance(description, str):
                raise ValidationError("Description must be a string")
            snippet["description"] = description.strip()

        if language is not None:
            if not language or not language.strip():
                raise ValidationError("Language cannot be empty")
            snippet["language"] = language.strip().lower()

        if tags is not None:
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise ValidationError("Tags must be a list of strings")
            snippet["tags"] = [tag.strip().lower() for tag in tags if tag.strip()]

        if code is not None:
            if not code or not isinstance(code, str):
                raise ValidationError("Code cannot be empty")
            snippet["code"] = code

        snippet["updated_at"] = self._generate_timestamp()
        self._save_storage()
        return True

    def delete_snippet(self, snippet_id: str) -> bool:
        """
        Delete a snippet by its ID.

        Args:
            snippet_id: Unique identifier of the snippet to delete.

        Returns:
            True if the snippet was deleted.

        Raises:
            SnippetNotFoundError: If the snippet does not exist.
            StorageError: If saving fails.
        """
        for i, snippet in enumerate(self._snippets):
            if snippet["id"] == snippet_id:
                del self._snippets[i]
                self._save_storage()
                return True
        raise SnippetNotFoundError(f"Snippet with ID '{snippet_id}' not found")

    def search_snippets(
        self,
        keyword: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search snippets by keyword, language, and/or tags.

        Args:
            keyword: Search in title, description, and code (case-insensitive).
            language: Filter by exact language match (case-insensitive).
            tags: Filter by tags (all must match, case-insensitive).

        Returns:
            List of matching snippets (most recent first).
        """
        results = []
        keyword_lower = keyword.lower() if keyword else None
        language_lower = language.lower() if language else None
        tags_lower = [tag.lower() for tag in tags] if tags else None

        for snippet in self._snippets:
            # Keyword match
            if keyword_lower:
                haystack = (
                    snippet["title"] + " " +
                    snippet["description"] + " " +
                    snippet["code"]
                ).lower()
                if keyword_lower not in haystack:
                    continue

            # Language match
            if language_lower and snippet["language"] != language_lower:
                continue

            # Tags match (all specified tags must be present)
            if tags_lower:
                snippet_tags = set(snippet["tags"])
                if not all(tag in snippet_tags for tag in tags_lower):
                    continue

            results.append(snippet)

        # Sort by updated_at descending (most recent first)
        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    def list_snippets(self) -> List[Dict[str, Any]]:
        """
        List all snippets, most recent first.

        Returns:
            List of all snippets sorted by update time descending.
        """
        snippets = self._snippets.copy()
        snippets.sort(key=lambda s: s["updated_at"], reverse=True)
        return snippets

    def _highlight_code(self, code: str, language: str) -> str:
        """
        Apply syntax highlighting to code using Pygments.

        Args:
            code: Source code to highlight.
            language: Programming language name.

        Returns:
            Highlighted code as a string (ANSI escape sequences for terminal).
        """
        if not PYGMENTS_AVAILABLE:
            return code

        try:
            lexer = get_lexer_by_name(language, stripall=True)
        except ClassNotFound:
            try:
                lexer = guess_lexer(code)
            except ClassNotFound:
                return code

        formatter = TerminalFormatter()
        return highlight(code, lexer, formatter)

    def display_snippet(self, snippet_id: str, highlight: bool = True) -> str:
        """
        Generate a formatted display string for a snippet.

        Args:
            snippet_id: Unique identifier of the snippet.
            highlight: Whether to apply syntax highlighting (if Pygments available).

        Returns:
            Formatted string representation of the snippet.

        Raises:
            SnippetNotFoundError: If the snippet does not exist.
        """
        snippet = self.get_snippet(snippet_id)

        lines = [
            f"ID: {snippet['id']}",
            f"Title: {snippet['title']}",
            f"Description: {snippet['description']}",
            f"Language: {snippet['language']}",
            f"Tags: {', '.join(snippet['tags']) if snippet['tags'] else 'None'}",
            f"Created: {snippet['created_at']}",
            f"Updated: {snippet['updated_at']}",
            "-" * 60,
            "Code:"
        ]

        code = snippet["code"]
        if highlight:
            code = self._highlight_code(code, snippet["language"])

        lines.append(code)
        return "\n".join(lines)


def _print_error(message: str) -> None:
    """Print error message to stderr."""
    print(f"Error: {message}", file=sys.stderr)


def _print_success(message: str) -> None:
    """Print success message to stdout."""
    print(f"Success: {message}")


def _parse_tags(tag_string: str) -> List[str]:
    """Parse comma-separated tag string into a list."""
    return [tag.strip() for tag in tag_string.split(",") if tag.strip()]


def main() -> None:
    """
    Command-line interface for the Snippet Manager.

    Commands:
        add      - Add a new snippet
        get      - Display a snippet by ID
        update   - Update an existing snippet
        delete   - Delete a snippet
        search   - Search snippets
        list     - List all snippets
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Code Snippet Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s add -t "Hello World" -d "Simple example" -l python -g "example,beginner" -c 'print("Hello")'
  %(prog)s get <snippet-id>
  %(prog)s search -k "hello" -l python
  %(prog)s list
        """
    )
    parser.add_argument(
        "--storage",
        default="snippets.json",
        help="Path to storage file (default: snippets.json)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new snippet")
    add_parser.add_argument("-t", "--title", required=True, help="Snippet title")
    add_parser.add_argument("-d", "--description", default="", help="Snippet description")
    add_parser.add_argument("-l", "--language", required=True, help="Programming language")
    add_parser.add_argument("-g", "--tags", default="", help="Comma-separated tags")
    add_parser.add_argument("-c", "--code", required=True, help="Source code")

    # Get command
    get_parser = subparsers.add_parser("get", help="Display a snippet")
    get_parser.add_argument("snippet_id", help="Snippet ID")
    get_parser.add_argument("--no-highlight", action="store_true", help="Disable syntax highlighting")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update a snippet")
    update_parser.add_argument("snippet_id", help="Snippet ID")
    update_parser.add_argument("-t", "--title", help="New title")
    update_parser.add_argument("-d", "--description", help="New description")
    update_parser.add_argument("-l", "--language", help="New language")
    update_parser.add_argument("-g", "--tags", help="New comma-separated tags")
    update_parser.add_argument("-c", "--code", help="New source code")

    # Delete command
    delete_parser = subparsers.add_parser("