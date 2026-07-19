"""
Task 18: Local Code Repository Management Workspace
Features: Multi-variable relational sorting, full text search filters, SQLite persistent memory models.
Requires: sqlite3 (Built-in standard library layer asset)
"""

import sqlite3
import sys
import logging
from typing import List, Dict, Tuple, Any, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SnippetStorageRepository:
    """Manages transactional query interactions with local SQL database memory backends."""
    
    def __init__(self, db_filename: str = "developer_vault.db") -> None:
        self.db_path = db_filename
        self._initialize_database_tables()

    def _get_connection_context(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Returns mapping definitions as dictionary rows
        return conn

    def _initialize_database_tables(self) -> None:
        """Builds local schemas if structural blocks are missing from disk allocation sectors."""
        with self._get_connection_context() as schema_transaction:
            schema_transaction.execute("""
                CREATE TABLE IF NOT EXISTS system_code_snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snippet_title TEXT NOT NULL UNIQUE,
                    syntax_language TEXT NOT NULL,
                    code_block TEXT NOT NULL,
                    description_note TEXT,
                    created_epoch TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            schema_transaction.commit()

    def persist_new_snippet(self, title: str, language: str, code: str, description: Optional[str] = None) -> bool:
        """Inserts snippet entries safely using parameterized queries to block SQL injection vectors."""
        query_string = """
            INSERT INTO system_code_snippets (snippet_title, syntax_language, code_block, description_note)
            VALUES (?, ?, ?, ?)
        """
        try:
            with self._get_connection_context() as insert_transaction:
                insert_transaction.execute(query_string, (title.strip(), language.strip().lower(), code, description))
                insert_transaction.commit()
            logger.info(f"Successfully committed configuration metadata snippet reference: {title}")
            return True
        except sqlite3.IntegrityError:
            logger.error(f"Execution rejected. Unique index violation identifier matched for key: {title}")
            return False

    def query_snippets_by_keyword(self, search_term: str) -> List[Dict[str, Any]]:
        """Queries records utilizing SQL LIKE operators against title, description, or code blocks."""
        query_string = """
            SELECT * FROM system_code_snippets 
            WHERE snippet_title LIKE ? OR description_note LIKE ? OR code_block LIKE ?
            ORDER BY created_epoch DESC
        """
        wildcard_term = f"%{search_term.strip()}%"
        with self._get_connection_context() as search_session:
            cursor_rows = search_session.execute(query_string, (wildcard_term, wildcard_term, wildcard_term)).fetchall()
            return [dict(row) for row in cursor_rows]

    def fetch_all_records(self) -> List[Dict[str, Any]]:
        """Extracts complete repository elements sorted chronologically by creation dates."""
        with self._get_connection_context() as view_session:
            cursor_rows = view_session.execute("SELECT * FROM system_code_snippets ORDER BY created_epoch DESC").fetchall()
            return [dict(row) for row in cursor_rows]

if __name__ == "__main__":
    vault = SnippetStorageRepository("test_dev_vault.db")
    
    # Inject Sample Blocks
    vault.persist_new_snippet(
        title="FastAPI Lifespan Startup Context Wrapper Handler",
        language="python",
        code="@asynccontextmanager\nasync def lifespan(app: FastAPI):\n    yield",
        description="Standard lifecycle configuration setup for setting up database connection strings pooling layers."
    )
    
    # Query Database
    matches = vault.query_snippets_by_keyword("FastAPI")
    print(f"\nExtracted Query Search Result Records Match Array Count: {len(matches)}")
    for item in matches:
        print(f"[-] Title: {item['snippet_title']} | Language: {item['syntax_language']}\n[Code Block]\n{item['code_block']}\n")
