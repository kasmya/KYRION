import hashlib
import hmac
import os
from typing import Dict, List, Optional
from flask import Flask, render_template, request, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
db = SQLAlchemy(app)

class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(200), nullable=False)
    code = db.Column(db.Text, nullable=False)
    hash = db.Column(db.String(64), nullable=False)

    def __init__(self, title, description, language, tags, code):
        self.title = title
        self.description = description
        self.language = language
        self.tags = tags
        self.code = code
        self.hash = self.generate_hash()

    def generate_hash(self):
        return hashlib.sha256(self.code.encode()).hexdigest()

    def get_highlighted_code(self):
        lexer = get_lexer_by_name(self.language)
        formatter = HtmlFormatter()
        return highlight(self.code, lexer, formatter)

    def __repr__(self):
        return f"Snippet('{self.title}', '{self.description}', '{self.language}', '{self.tags}')"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/snippets", methods=["GET", "POST"])
def snippets():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        language = request.form["language"]
        tags = request.form["tags"]
        code = request.form["code"]
        snippet = Snippet(title, description, language, tags, code)
        db.session.add(snippet)
        db.session.commit()
        return redirect(url_for("snippet", id=snippet.id))
    return render_template("snippets.html", snippets=Snippet.query.all())

@app.route("/snippets/<int:id>", methods=["GET", "POST"])
def snippet(id: int):
    snippet = Snippet.query.get_or_404(id)
    if request.method == "POST":
        if hmac.compare_digest(request.form["password"], os.environ.get("EDIT_PASSWORD")):
            snippet.title = request.form["title"]
            snippet.description = request.form["description"]
            snippet.language = request.form["language"]
            snippet.tags = request.form["tags"]
            snippet.code = request.form["code"]
            db.session.commit()
        else:
            abort(403)
    return render_template("snippet.html", snippet=snippet, highlighted_code=snippet.get_highlighted_code())

@app.route("/snippets/<int:id>/delete", methods=["POST"])
def delete_snippet(id: int):
    snippet = Snippet.query.get_or_404(id)
    if hmac.compare_digest(request.form["password"], os.environ.get("DELETE_PASSWORD")):
        db.session.delete(snippet)
        db.session.commit()
        return redirect(url_for("snippets"))
    else:
        abort(403)

@app.route("/search", methods=["GET"])
def search():
    keyword = request.args.get("keyword")
    language = request.args.get("language")
    if keyword:
        snippets = Snippet.query.filter(Snippet.title.like(f"%{keyword}%") | Snippet.description.like(f"%{keyword}%")).all()
    elif language:
        snippets = Snippet.query.filter_by(language=language).all()
    else:
        snippets = []
    return render_template("search.html", snippets=snippets)

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)