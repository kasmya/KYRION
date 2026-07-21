"""
Code Snippet Manager

A command-line tool for managing code snippets with title, description, language, and tags.
Supports saving, searching, editing, deleting, and displaying snippets with syntax highlighting.

Dependencies:
    - pygments (for syntax highlighting): pip install pygments
"""

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.util import ClassNotFound
except ImportError:
    print("Error: pygments is required for syntax highlighting. Install with: pip install pygments")
    sys.exit(1)


@dataclass
class Snippet:
    """Represents a code snippet with metadata."""
    id: str
    title: str
    description: str
    language: str
    code: str
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SnippetManager:
    """Manages storage and retrieval of code snippets."""

    def __init__(self, storage_path: Path) -> None:
        """
        Initialize the snippet manager.

        Args:
            storage_path: Path to the JSON file for storing snippets.
        """
        self.storage_path = storage_path
        self.snippets: Dict[str, Snippet] = {}
        self._load()

    def _load(self) -> None:
        """Load snippets from the storage file."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.snippets = {
                    item["id"]: Snippet(**item) for item in data.get("snippets", [])
                }
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"Warning: Could not load snippets from {self.storage_path}: {e}")
                self.snippets = {}
        else:
            self.snippets = {}

    def _save(self) -> None:
        """Save snippets to the storage file."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"snippets": [asdict(s) for s in self.snippets.values()]},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except (OSError, TypeError) as e:
            raise RuntimeError(f"Failed to save snippets: {e}") from e

    def add(
        self,
        title: str,
        description: str,
        language: str,
        code: str,
        tags: Optional[List[str]] = None,
    ) -> Snippet:
        """
        Add a new snippet.

        Args:
            title: Snippet title.
            description: Snippet description.
            language: Programming language.
            code: Source code.
            tags: List of tags.

        Returns:
            The created Snippet object.

        Raises:
            ValueError: If title or code is empty.
        """
        if not title.strip():
            raise ValueError("Title cannot be empty")
        if not code.strip():
            raise ValueError("Code cannot be empty")

        snippet = Snippet(
            id=str(uuid.uuid4()),
            title=title.strip(),
            description=description.strip(),
            language=language.strip().lower(),
            code=code.rstrip(),
            tags=[tag.strip().lower() for tag in (tags or []) if tag.strip()],
        )
        self.snippets[snippet.id] = snippet
        self._save()
        return snippet

    def get(self, snippet_id: str) -> Optional[Snippet]:
        """
        Retrieve a snippet by ID.

        Args:
            snippet_id: The snippet's unique identifier.

        Returns:
            The Snippet if found, else None.
        """
        return self.snippets.get(snippet_id)

    def update(
        self,
        snippet_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        language: Optional[str] = None,
        code: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Snippet]:
        """
        Update an existing snippet.

        Args:
            snippet_id: The snippet's unique identifier.
            title: New title (optional).
            description: New description (optional).
            language: New language (optional).
            code: New code (optional).
            tags: New tags (optional).

        Returns:
            The updated Snippet if found, else None.

        Raises:
            ValueError: If title or code is set to empty string.
        """
        snippet = self.snippets.get(snippet_id)
        if not snippet:
            return None

        if title is not None:
            if not title.strip():
                raise ValueError("Title cannot be empty")
            snippet.title = title.strip()
        if description is not None:
            snippet.description = description.strip()
        if language is not None:
            snippet.language = language.strip().lower()
        if code is not None:
            if not code.strip():
                raise ValueError("Code cannot be empty")
            snippet.code = code.rstrip()
        if tags is not None:
            snippet.tags = [tag.strip().lower() for tag in tags if tag.strip()]

        snippet.updated_at = datetime.now().isoformat()
        self._save()
        return snippet

    def delete(self, snippet_id: str) -> bool:
        """
        Delete a snippet by ID.

        Args:
            snippet_id: The snippet's unique identifier.

        Returns:
            True if deleted, False if not found.
        """
        if snippet_id in self.snippets:
            del self.snippets[snippet_id]
            self._save()
            return True
        return False

    def search(
        self,
        keyword: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Snippet]:
        """
        Search snippets by keyword, language, and/or tags.

        Args:
            keyword: Search in title, description, and code (case-insensitive).
            language: Filter by programming language (case-insensitive).
            tags: Filter by tags (all must match, case-insensitive).

        Returns:
            List of matching snippets, sorted by updated_at descending.
        """
        results = list(self.snippets.values())
        keyword_lower = keyword.lower() if keyword else None
        language_lower = language.lower() if language else None
        tags_lower = {tag.lower() for tag in tags} if tags else None

        if keyword_lower:
            results = [
                s
                for s in results
                if (
                    keyword_lower in s.title.lower()
                    or keyword_lower in s.description.lower()
                    or keyword_lower in s.code.lower()
                    or any(keyword_lower in tag for tag in s.tags)
                )
            ]

        if language_lower:
            results = [s for s in results if s.language == language_lower]

        if tags_lower:
            results = [s for s in results if tags_lower.issubset(set(s.tags))]

        results.sort(key=lambda s: s.updated_at, reverse=True)
        return results

    def list_all(self) -> List[Snippet]:
        """Return all snippets sorted by updated_at descending."""
        return sorted(self.snippets.values(), key=lambda s: s.updated_at, reverse=True)

    def get_languages(self) -> Set[str]:
        """Return a set of all languages used in snippets."""
        return {s.language for s in self.snippets.values()}

    def get_tags(self) -> Set[str]:
        """Return a set of all tags used in snippets."""
        tags = set()
        for s in self.snippets.values():
            tags.update(s.tags)
        return tags


def highlight_code(code: str, language: str) -> str:
    """
    Apply syntax highlighting to code.

    Args:
        code: Source code string.
        language: Programming language name.

    Returns:
        Highlighted code string for terminal output.
    """
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except ClassNotFound:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            return code
    formatter = TerminalFormatter()
    return highlight(code, lexer, formatter)


def print_snippet(snippet: Snippet, highlight_syntax: bool = True) -> None:
    """
    Print a snippet in a formatted way.

    Args:
        snippet: The Snippet to print.
        highlight_syntax: Whether to apply syntax highlighting.
    """
    print(f"\n{'=' * 60}")
    print(f"ID:          {snippet.id}")
    print(f"Title:       {snippet.title}")
    print(f"Description: {snippet.description or '(none)'}")
    print(f"Language:    {snippet.language}")
    print(f"Tags:        {', '.join(snippet.tags) if snippet.tags else '(none)'}")
    print(f"Created:     {snippet.created_at}")
    print(f"Updated:     {snippet.updated_at}")
    print(f"{'-' * 60}")
    print("Code:")
    code_output = (
        highlight_code(snippet.code, snippet.language)
        if highlight_syntax
        else snippet.code
    )
    print(code_output.rstrip())
    print(f"{'=' * 60}\n")


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Code Snippet Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s add -t "Quick Sort" -d "Python implementation" -l python -c "def quicksort(arr): ..."
  %(prog)s search -k "sort" -l python
  %(prog)s edit <id> -t "New Title"
  %(prog)s delete <id>
  %(prog)s list
        """,
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=Path.home() / ".snippets.json",
        help="Path to storage file (default: ~/.snippets.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new snippet")
    add_parser.add_argument("-t", "--title", required=True, help="Snippet title")
    add_parser.add_argument("-d", "--description", default="", help="Snippet description")
    add_parser.add_argument("-l", "--language", required=True, help="Programming language")
    add_parser.add_argument("-c", "--code", required=True, help="Source code")
    add_parser.add_argument("--tags", nargs="*", default=[], help="Tags (space-separated)")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search snippets")
    search_parser.add_argument("-k", "--keyword", help="Search keyword")
    search_parser.add_argument("-l", "--language", help="Filter by language")
    search_parser.add_argument("--tags", nargs="*", default=[], help="Filter by tags (all must match)")

    # Edit command
    edit_parser = subparsers.add_parser("edit", help="Edit an existing snippet")
    edit_parser.add_argument("id", help="Snippet ID")
    edit_parser.add_argument("-t", "--title", help="New title")
    edit_parser.add_argument("-d", "--description", help="New description")
    edit_parser.add_argument("-l", "--language", help="New language")
    edit_parser.add_argument("-c", "--code", help="New code")
    edit_parser.add_argument("--tags", nargs="*", help="New tags (replaces existing)")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a snippet")
    delete_parser.add_argument("id", help="Snippet ID")

    # List command
    list_parser = subparsers.add_parser("list", help="List all snippets")
    list_parser.add_argument("--no-highlight", action="store_true", help="Disable syntax highlighting")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show a snippet by ID")
    show_parser.add_argument("id", help="Snippet ID")
    show_parser.add_argument("--no-highlight", action="store_true", help="Disable syntax highlighting")

    # Languages command
    subparsers.add_parser("languages", help="List all languages used")

    # Tags command
    subparsers.add_parser("tags", help="List all tags used")

    args = parser.parse_args()

    manager = SnippetManager(args.storage)

    try:
        if args.command == "add":
            snippet = manager.add(
                title=args.title,
                description=args.description,
                language=args.language,
                code=args.code,
                tags=args.tags,
            )
            print(f"Added snippet with ID: {snippet.id}")

        elif args.command == "search":
            results = manager.search(
                keyword=args.keyword,
                language=args.language,
                tags=args.tags if args.tags else None,
            )
            if not results:
                print("No snippets found.")
            else:
                print(f"Found {len(results)} snippet(s):")
                for snippet in results:
                    print_snippet(snippet, highlight_syntax=True)

        elif args.command == "edit":
            snippet = manager.update(
                snippet_id=args.id,
                title=args.title,
                description=args.description,
                language=args.language,
                code=args.code,
                tags=args.tags,
            )
            if snippet:
                print(f"Updated snippet: {snippet.id}")
            else:
                print(f"Snippet not found: {args.id}", file=sys.stderr)
                sys.exit(1)

        elif args.command == "delete":
            if manager.delete(args.id):
                print(f"Deleted snippet: {args.id}")
            else:
                print(f"Snippet not found: {args.id}", file=sys.stderr)
                sys.exit(1)

        elif args.command == "list":
            snippets = manager.list_all()
            if not snippets:
                print("No snippets saved.")
            else:
                print(f"Total snippets: {len(snippets)}")
                for snippet in snippets:
                    print_snippet(snippet, highlight_syntax=not args.no_highlight)

        elif args.command == "show":
            snippet = manager.get(args.id)
            if snippet:
                print_snippet(snippet, highlight_syntax=not args.no_highlight)
            else:
                print(f"Snippet not found: {args.id}", file=sys.stderr)
                sys.exit(1)

        elif args.command == "languages":
            languages = manager.get_languages()
            if languages:
                print("Languages used:")
                for lang in sorted(languages):
                    print(f"  {lang}")
            else:
                print("No languages found.")

        elif args.command == "tags":
            tags = manager.get_tags()
            if tags:
                print("Tags used:")
                for tag in sorted(tags):
                    print(f"  {tag}")
            else:
                print("No tags found.")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()