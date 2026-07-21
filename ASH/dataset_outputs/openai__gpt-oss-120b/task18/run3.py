"""
Snippet Manager Module
---------------------

A lightweight manager for code snippets supporting creation, retrieval,
search, update, deletion, and pretty display with syntax highlighting.

Features
~~~~~~~~
* Store snippets with title, description, language, tags, and source code.
* Search snippets by keyword (title/description/tags/code) or by language.
* Edit and delete existing snippets.
* Render snippets with syntax highlighting using Pygments.

The implementation uses SQLite (via the standard library) for persistence and
Pygments for terminal colour output. All database interactions are performed
with parameterised queries to avoid SQL injection.

Typical usage
~~~~~~~~~~~~~
>>> from snippet_manager import SnippetManager
>>> mgr = SnippetManager()
>>> mgr.add_snippet(
...     title="Hello World",
...     description="Prints hello world",
...     language="python",
...     tags=["example", "intro"],
...     code='print("Hello, world!")',
... )
>>> snippets = mgr.search_by_keyword("hello")
>>> mgr.display_snippet(snippets[0]["id"])
"""

from __future__ import annotations

import os
import sqlite3
import sys
import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

# Pygments is a widely‑used library for syntax highlighting.
# It is safe to import as it is a pure‑Python dependency.
try:
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers import get_lexer_by_name, guess_lexer
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Pygments is required for snippet display. Install it via "
        "`pip install pygments`."
    ) from exc


class SnippetError(Exception):
    """Base class for all snippet‑related errors."""


class SnippetNotFoundError(SnippetError):
    """Raised when a snippet with the requested identifier does not exist."""


class SnippetManager:
    """
    Manage code snippets persisted in a SQLite database.

    Parameters
    ----------
    db_path : str | os.PathLike, optional
        Path to the SQLite database file. If omitted, a file named
        ``snippets.db`` is created in the user's configuration directory.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS snippets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        language TEXT NOT NULL,
        tags TEXT,
        code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """

    def __init__(self, db_path: os.PathLike | str | None = None) -> None:
        self.db_path = Path(
            db_path
            or Path.home() / ".config" / "snippet_manager" / "snippets.db"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create the database schema if it does not already exist."""
        try:
            with self._conn:
                self._conn.executescript(self._SCHEMA)
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Failed to initialise the snippets database.") from exc

    # --------------------------------------------------------------------- #
    # CRUD operations
    # --------------------------------------------------------------------- #

    def add_snippet(
        self,
        *,
        title: str,
        description: str,
        language: str,
        tags: Sequence[str],
        code: str,
    ) -> int:
        """
        Insert a new snippet into the database.

        Returns
        -------
        int
            The identifier of the newly created snippet.

        Raises
        ------
        SnippetError
            If the insertion fails.
        """
        now = _dt.datetime.utcnow().isoformat()
        tags_csv = ",".join(sorted(set(tag.strip() for tag in tags if tag.strip())))

        query = """
        INSERT INTO snippets (title, description, language, tags, code, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (title, description, language, tags_csv, code, now, now)

        try:
            with self._conn:
                cur = self._conn.execute(query, params)
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise SnippetError("Failed to add snippet due to integrity constraints.") from exc
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Database error while adding snippet.") from exc

    def get_snippet(self, snippet_id: int) -> Dict[str, Any]:
        """
        Retrieve a snippet by its identifier.

        Parameters
        ----------
        snippet_id : int
            Identifier of the snippet.

        Returns
        -------
        dict
            Mapping of column names to values.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        SnippetError
            For other database failures.
        """
        query = "SELECT * FROM snippets WHERE id = ?"
        try:
            cur = self._conn.execute(query, (snippet_id,))
            row = cur.fetchone()
            if row is None:
                raise SnippetNotFoundError(f"Snippet with id {snippet_id} not found.")
            return dict(row)
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Failed to retrieve snippet.") from exc

    def edit_snippet(
        self,
        snippet_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        language: str | None = None,
        tags: Sequence[str] | None = None,
        code: str | None = None,
    ) -> None:
        """
        Update fields of an existing snippet.

        Only provided arguments are updated; others remain unchanged.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        SnippetError
            If the update fails.
        """
        existing = self.get_snippet(snippet_id)  # May raise SnippetNotFoundError

        updates: List[str] = []
        params: List[Any] = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if language is not None:
            updates.append("language = ?")
            params.append(language)
        if tags is not None:
            tags_csv = ",".join(sorted(set(tag.strip() for tag in tags if tag.strip())))
            updates.append("tags = ?")
            params.append(tags_csv)
        if code is not None:
            updates.append("code = ?")
            params.append(code)

        if not updates:
            # Nothing to change; silently succeed.
            return

        updates.append("updated_at = ?")
        params.append(_dt.datetime.utcnow().isoformat())
        params.append(snippet_id)

        query = f"UPDATE snippets SET {', '.join(updates)} WHERE id = ?"

        try:
            with self._conn:
                cur = self._conn.execute(query, tuple(params))
                if cur.rowcount == 0:
                    raise SnippetNotFoundError(f"Snippet with id {snippet_id} not found.")
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Failed to edit snippet.") from exc

    def delete_snippet(self, snippet_id: int) -> None:
        """
        Remove a snippet from the database.

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        SnippetError
            For other database errors.
        """
        query = "DELETE FROM snippets WHERE id = ?"
        try:
            with self._conn:
                cur = self._conn.execute(query, (snippet_id,))
                if cur.rowcount == 0:
                    raise SnippetNotFoundError(f"Snippet with id {snippet_id} not found.")
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Failed to delete snippet.") from exc

    # --------------------------------------------------------------------- #
    # Search utilities
    # --------------------------------------------------------------------- #

    def search_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search snippets containing the keyword in title, description, tags, or code.

        Parameters
        ----------
        keyword : str
            Case‑insensitive search term.

        Returns
        -------
        list[dict]
            List of matching snippets (as dictionaries).
        """
        pattern = f"%{keyword.lower()}%"
        query = """
        SELECT * FROM snippets
        WHERE LOWER(title) LIKE ?
           OR LOWER(description) LIKE ?
           OR LOWER(tags) LIKE ?
           OR LOWER(code) LIKE ?
        ORDER BY updated_at DESC
        """
        try:
            cur = self._conn.execute(
                query, (pattern, pattern, pattern, pattern)
            )
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Keyword search failed.") from exc

    def search_by_language(self, language: str) -> List[Dict[str, Any]]:
        """
        Retrieve snippets written in the specified programming language.

        Parameters
        ----------
        language : str
            Language name (case‑insensitive).

        Returns
        -------
        list[dict]
            Matching snippets.
        """
        query = """
        SELECT * FROM snippets
        WHERE LOWER(language) = ?
        ORDER BY updated_at DESC
        """
        try:
            cur = self._conn.execute(query, (language.lower(),))
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.DatabaseError as exc:
            raise SnippetError("Language search failed.") from exc

    # --------------------------------------------------------------------- #
    # Display
    # --------------------------------------------------------------------- #

    def display_snippet(self, snippet_id: int, *, stream: Any = sys.stdout) -> None:
        """
        Render a snippet with syntax highlighting to the provided stream.

        Parameters
        ----------
        snippet_id : int
            Identifier of the snippet to display.
        stream : file‑like, optional
            Destination for the highlighted output (defaults to ``sys.stdout``).

        Raises
        ------
        SnippetNotFoundError
            If the snippet does not exist.
        SnippetError
            If highlighting fails.
        """
        snippet = self.get_snippet(snippet_id)

        code = snippet["code"]
        language = snippet["language"]

        try:
            lexer = get_lexer_by_name(language, stripall=True)
        except Exception:  # pragma: no cover
            # Fallback to guessing if language is unknown to Pygments.
            try:
                lexer = guess_lexer(code)
            except Exception as exc:
                raise SnippetError(f"Unable to find a lexer for language '{language}'.") from exc

        formatter = TerminalFormatter()
        highlighted = highlight(code, lexer, formatter)

        header = (
            f"Title      : {snippet['title']}\n"
            f"Language   : {snippet['language']}\n"
            f"Tags       : {snippet['tags'] or ''}\n"
            f"Created at : {snippet['created_at']}\n"
            f"Updated at : {snippet['updated_at']}\n"
            f"{'-'*40}"
        )
        try:
            stream.write(header + "\n")
            stream.write(highlighted)
            stream.flush()
        except Exception as exc:
            raise SnippetError("Failed to write highlighted snippet.") from exc

    # --------------------------------------------------------------------- #
    # Utility / cleanup
    # --------------------------------------------------------------------- #

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            self._conn.close()
        except Exception as exc:  # pragma: no cover
            raise SnippetError("Failed to close database connection.") from exc

    def __enter__(self) -> "SnippetManager":
        """Enable use as a context manager."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        """Automatically close the connection when exiting a context."""
        self.close()