from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
import re
from http import HTTPStatus
from flask import Flask, request, jsonify
from markupsafe import Markup
import pygments
from pygments.lexers import guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter

app = Flask(__name__)

@dataclass
class Snippet:
    """Represents a code snippet."""
    id: int
    title: str
    description: str
    language: str
    tags: List[str]
    code: str

    def to_dict(self) -> Dict:
        """Converts the snippet to a dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "tags": self.tags,
            "code": self.code,
        }

class SnippetManager:
    """Manages a collection of code snippets."""
    def __init__(self):
        self.snippets: Dict[int, Snippet] = {}
        self.next_id: int = 1

    def add_snippet(self, title: str, description: str, language: str, tags: List[str], code: str) -> Snippet:
        """Adds a new snippet to the manager."""
        snippet = Snippet(self.next_id, title, description, language, tags, code)
        self.snippets[self.next_id] = snippet
        self.next_id += 1
        return snippet

    def get_snippet(self, id: int) -> Optional[Snippet]:
        """Retrieves a snippet by ID."""
        return self.snippets.get(id)

    def delete_snippet(self, id: int) -> bool:
        """Deletes a snippet by ID."""
        if id in self.snippets:
            del self.snippets[id]
            return True
        return False

    def edit_snippet(self, id: int, **updates) -> bool:
        """Edits a snippet by ID."""
        snippet = self.get_snippet(id)
        if snippet:
            for key, value in updates.items():
                if hasattr(snippet, key):
                    setattr(snippet, key, value)
            return True
        return False

    def search_snippets(self, keyword: str = None, language: str = None) -> List[Snippet]:
        """Searches for snippets by keyword or language."""
        results = list(self.snippets.values())
        if keyword:
            results = [s for s in results if re.search(keyword, s.title + s.description + ' '.join(s.tags) + s.code)]
        if language:
            results = [s for s in results if s.language.lower() == language.lower()]
        return results

    def highlight_snippet(self, snippet: Snippet) -> str:
        """Highlights the code of a snippet using Pygments."""
        try:
            lexer = guess_lexer(snippet.code, linenos=True)
        except ValueError:
            lexer = TextLexer()
        formatter = HtmlFormatter(linenos=True)
        return pygments.highlight(snippet.code, lexer, formatter)

snippet_manager = SnippetManager()

@app.route("/snippets", methods=["POST"])
def create_snippet():
    """Creates a new snippet."""
    data = request.json
    if not data:
        return jsonify({"error": "Missing request body"}), HTTPStatus.BAD_REQUEST
    
    required_fields = ["title", "description", "language", "tags", "code"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), HTTPStatus.BAD_REQUEST
    
    try:
        snippet = snippet_manager.add_snippet(
            data["title"],
            data["description"],
            data["language"],
            data["tags"],
            data["code"]
        )
        return jsonify(snippet.to_dict()), HTTPStatus.CREATED
    except Exception as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/snippets/<int:snippet_id>", methods=["GET"])
def get_snippet(snippet_id: int):
    """Retrieves a snippet by ID."""
    snippet = snippet_manager.get_snippet(snippet_id)
    if not snippet:
        return jsonify({"error": "Snippet not found"}), HTTPStatus.NOT_FOUND
    highlighted_code = snippet_manager.highlight_snippet(snippet)
    snippet_dict = snippet.to_dict()
    snippet_dict["highlighted_code"] = Markup(highlighted_code)  # Use Markup for safe HTML
    return jsonify(snippet_dict)

@app.route("/snippets/<int:snippet_id>", methods=["PUT"])
def update_snippet(snippet_id: int):
    """Updates a snippet."""
    snippet = snippet_manager.get_snippet(snippet_id)
    if not snippet:
        return jsonify({"error": "Snippet not found"}), HTTPStatus.NOT_FOUND
    
    data = request.json
    if not data:
        return jsonify({"error": "Missing request body"}), HTTPStatus.BAD_REQUEST
    
    try:
        if snippet_manager.edit_snippet(snippet_id, **data):
            return jsonify(snippet_manager.get_snippet(snippet_id).to_dict())
        else:
            return jsonify({"error": "Failed to update snippet"}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

@app.route("/snippets/<int:snippet_id>", methods=["DELETE"])
def delete_snippet(snippet_id: int):
    """Deletes a snippet."""
    if snippet_manager.delete_snippet(snippet_id):
        return jsonify({"message": "Snippet deleted successfully"})
    else:
        return jsonify({"error": "Snippet not found"}), HTTPStatus.NOT_FOUND

@app.route("/snippets/search", methods=["GET"])
def search_snippets():
    """Searches for snippets."""
    keyword = request.args.get("keyword")
    language = request.args.get("language")
    snippets = snippet_manager.search_snippets(keyword, language)
    return jsonify([s.to_dict() for s in snippets])

if __name__ == "__main__":
    app.run(debug=True)