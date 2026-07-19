"""
Code Snippet Manager using Flask, SQLAlchemy, Pygments, and Markdown.
Features:
- Create, edit, delete snippets
- Syntax highlighting
- Search by tag or content
- Export snippets (Markdown, HTML)
"""

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter
import markdown
import logging

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
db = SQLAlchemy(app)
logging.basicConfig(level=logging.INFO)


class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    code = db.Column(db.Text)
    tags = db.Column(db.String(100))


@app.route("/create", methods=["POST"])
def create():
    data = request.json
    snippet = Snippet(title=data["title"], code=data["code"], tags=data.get("tags", ""))
    db.session.add(snippet)
    db.session.commit()
    return jsonify({"msg": "Snippet created"})


@app.route("/search")
def search():
    q = request.args.get("q", "")
    results = Snippet.query.filter(Snippet.code.contains(q) | Snippet.tags.contains(q)).all()
    return jsonify([{"title": s.title, "code": s.code, "tags": s.tags} for s in results])


@app.route("/export/<int:id>")
def export(id: int):
    snippet = Snippet.query.get(id)
    if not snippet:
        return jsonify({"error": "Not found"}), 404
    highlighted = highlight(snippet.code, PythonLexer(), HtmlFormatter())
    md = markdown.markdown(snippet.code)
    return jsonify({"html": highlighted, "markdown": md})


if __name__ == "__main__":
    with app.app_context():

