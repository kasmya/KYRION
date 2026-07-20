from typing import List, Dict, Optional
from dataclasses import dataclass
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
db = SQLAlchemy(app)

@dataclass
class Snippet:
    """Data class representing a code snippet."""
    id: int
    title: str
    description: str
    language: str
    tags: List[str]
    code: str

class SnippetModel(db.Model):
    """Database model for a code snippet."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(100), nullable=False)
    code = db.Column(db.Text, nullable=False)

    def to_dict(self) -> Dict:
        """Convert the model to a dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "tags": self.tags.split(","),
            "code": self.code,
        }

@app.route("/snippets", methods=["POST"])
def create_snippet() -> Dict:
    """Create a new code snippet."""
    data = request.get_json()
    if not data:
        return {"error": "Invalid request"}, 400

    title = data.get("title")
    description = data.get("description")
    language = data.get("language")
    tags = data.get("tags")
    code = data.get("code")

    if not all([title, description, language, tags, code]):
        return {"error": "Missing required fields"}, 400

    snippet = SnippetModel(
        title=title,
        description=description,
        language=language,
        tags=','.join(tags),
        code=code,
    )
    db.session.add(snippet)
    db.session.commit()

    return snippet.to_dict()

@app.route("/snippets", methods=["GET"])
def get_snippets() -> List[Dict]:
    """Get all code snippets."""
    snippets = SnippetModel.query.all()
    return [snippet.to_dict() for snippet in snippets]

@app.route("/snippets/<int:snippet_id>", methods=["GET"])
def get_snippet(snippet_id: int) -> Dict:
    """Get a code snippet by ID."""
    snippet = SnippetModel.query.get(snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, 404

    return snippet.to_dict()

@app.route("/snippets/search", methods=["GET"])
def search_snippets() -> List[Dict]:
    """Search code snippets by keyword or language."""
    query = request.args.get("query")
    language = request.args.get("language")

    snippets = SnippetModel.query.filter(
        (SnippetModel.title.like(f"%{query}%")) |
        (SnippetModel.description.like(f"%{query}%")) |
        (SnippetModel.tags.like(f"%{query}%")) |
        (SnippetModel.language == language)
    ).all()

    return [snippet.to_dict() for snippet in snippets]

@app.route("/snippets/<int:snippet_id>", methods=["PUT"])
def update_snippet(snippet_id: int) -> Dict:
    """Update a code snippet."""
    snippet = SnippetModel.query.get(snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, 404

    data = request.get_json()
    if not data:
        return {"error": "Invalid request"}, 400

    snippet.title = data.get("title", snippet.title)
    snippet.description = data.get("description", snippet.description)
    snippet.language = data.get("language", snippet.language)
    snippet.tags = data.get("tags", snippet.tags)
    snippet.code = data.get("code", snippet.code)

    db.session.commit()

    return snippet.to_dict()

@app.route("/snippets/<int:snippet_id>", methods=["DELETE"])
def delete_snippet(snippet_id: int) -> Dict:
    """Delete a code snippet."""
    snippet = SnippetModel.query.get(snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, 404

    db.session.delete(snippet)
    db.session.commit()

    return {"message": "Snippet deleted successfully"}

@app.route("/snippets/<int:snippet_id>/highlight", methods=["GET"])
def highlight_snippet(snippet_id: int) -> str:
    """Highlight a code snippet."""
    snippet = SnippetModel.query.get(snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, 404

    lexer = get_lexer_by_name(snippet.language)
    formatter = HtmlFormatter()
    highlighted_code = highlight(snippet.code, lexer, formatter)

    return highlighted_code

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)