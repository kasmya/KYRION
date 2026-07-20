from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from typing import Dict, List
import os
import secrets

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex()
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
db = SQLAlchemy(app)

class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    code = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(100), nullable=False)

    def to_dict(self) -> Dict:
        """Return a dictionary representation of the snippet."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "code": self.code,
            "tags": self.tags.split(","),
        }

@app.route("/snippets", methods=["POST"])
def create_snippet() -> Dict:
    """
    Create a new snippet.

    :return: The newly created snippet as a dictionary.
    """
    data = request.json
    snippet = Snippet(
        title=data["title"],
        description=data["description"],
        language=data["language"],
        code=data["code"],
        tags=",".join(data["tags"]),
    )
    db.session.add(snippet)
    db.session.commit()
    return snippet.to_dict()

@app.route("/snippets", methods=["GET"])
def get_snippets() -> List[Dict]:
    """
    Get all snippets.

    :return: A list of snippets as dictionaries.
    """
    snippets = Snippet.query.all()
    return [snippet.to_dict() for snippet in snippets]

@app.route("/snippets/<int:snippet_id>", methods=["GET"])
def get_snippet(snippet_id: int) -> Dict:
    """
    Get a snippet by ID.

    :param snippet_id: The ID of the snippet.
    :return: The snippet as a dictionary.
    """
    snippet = Snippet.query.get(snippet_id)
    if snippet is None:
        return {"error": "Snippet not found"}, 404
    return snippet.to_dict()

@app.route("/snippets/<int:snippet_id>", methods=["PUT"])
def edit_snippet(snippet_id: int) -> Dict:
    """
    Edit a snippet.

    :param snippet_id: The ID of the snippet.
    :return: The edited snippet as a dictionary.
    """
    snippet = Snippet.query.get(snippet_id)
    if snippet is None:
        return {"error": "Snippet not found"}, 404
    data = request.json
    snippet.title = data["title"]
    snippet.description = data["description"]
    snippet.language = data["language"]
    snippet.code = data["code"]
    snippet.tags = ",".join(data["tags"])
    db.session.commit()
    return snippet.to_dict()

@app.route("/snippets/<int:snippet_id>", methods=["DELETE"])
def delete_snippet(snippet_id: int) -> Dict:
    """
    Delete a snippet.

    :param snippet_id: The ID of the snippet.
    :return: A success message.
    """
    snippet = Snippet.query.get(snippet_id)
    if snippet is None:
        return {"error": "Snippet not found"}, 404
    db.session.delete(snippet)
    db.session.commit()
    return {"message": "Snippet deleted successfully"}

@app.route("/snippets/search", methods=["GET"])
def search_snippets() -> List[Dict]:
    """
    Search for snippets by keyword or language.

    :return: A list of matching snippets as dictionaries.
    """
    keyword = request.args.get("keyword")
    language = request.args.get("language")
    snippets = Snippet.query.all()
    results = []
    for snippet in snippets:
        if keyword and keyword in snippet.title or keyword in snippet.description:
            results.append(snippet.to_dict())
        elif language and language == snippet.language:
            results.append(snippet.to_dict())
    return results

@app.route("/snippets/<int:snippet_id>/highlight", methods=["GET"])
def highlight_snippet(snippet_id: int) -> str:
    """
    Highlight a snippet's code.

    :param snippet_id: The ID of the snippet.
    :return: The highlighted code as HTML.
    """
    snippet = Snippet.query.get(snippet_id)
    if snippet is None:
        return {"error": "Snippet not found"}, 404
    lexer = get_lexer_by_name(snippet.language)
    formatter = HtmlFormatter()
    highlighted_code = highlight(snippet.code, lexer, formatter)
    return highlighted_code

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)