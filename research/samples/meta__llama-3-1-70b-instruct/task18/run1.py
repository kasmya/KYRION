import sqlite3
import pygments
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from flask import Flask, request, render_template, redirect, url_for, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired
from typing import Optional, List

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret_key_here"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
db = SQLAlchemy(app)


class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    language = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(100), nullable=False)
    code = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"Snippet('{self.title}', '{self.language}')"


class SnippetForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    description = StringField("Description", validators=[DataRequired()])
    language = SelectField(
        "Language",
        choices=[
            ("python", "Python"),
            ("java", "Java"),
            ("javascript", "JavaScript"),
            ("c", "C"),
            ("c++", "C++"),
        ],
        validators=[DataRequired()],
    )
    tags = StringField("Tags", validators=[DataRequired()])
    code = TextAreaField("Code", validators=[DataRequired()])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/snippets")
def snippets():
    snippets = Snippet.query.all()
    return render_template("snippets.html", snippets=snippets)


@app.route("/snippet/<int:snippet_id>")
def snippet(snippet_id: int):
    snippet = Snippet.query.get_or_404(snippet_id)
    lexer = get_lexer_by_name(snippet.language)
    formatter = HtmlFormatter(linenos=True)
    code = pygments.highlight(snippet.code, lexer, formatter)
    return render_template("snippet.html", snippet=snippet, code=code)


@app.route("/snippet/<int:snippet_id>/edit", methods=["GET", "POST"])
def edit_snippet(snippet_id: int):
    snippet = Snippet.query.get_or_404(snippet_id)
    form = SnippetForm(obj=snippet)
    if form.validate_on_submit():
        form.populate_obj(snippet)
        db.session.commit()
        return redirect(url_for("snippet", snippet_id=snippet.id))
    return render_template("edit_snippet.html", form=form)


@app.route("/snippet/<int:snippet_id>/delete")
def delete_snippet(snippet_id: int):
    snippet = Snippet.query.get_or_404(snippet_id)
    db.session.delete(snippet)
    db.session.commit()
    return redirect(url_for("snippets"))


@app.route("/snippet/new", methods=["GET", "POST"])
def new_snippet():
    form = SnippetForm()
    if form.validate_on_submit():
        snippet = Snippet(
            title=form.title.data,
            description=form.description.data,
            language=form.language.data,
            tags=form.tags.data,
            code=form.code.data,
        )
        db.session.add(snippet)
        db.session.commit()
        return redirect(url_for("snippet", snippet_id=snippet.id))
    return render_template("new_snippet.html", form=form)


@app.route("/search")
def search():
    keyword = request.args.get("keyword")
    language = request.args.get("language")
    snippets = Snippet.query.all()
    if keyword:
        snippets = [snippet for snippet in snippets if keyword in snippet.title]
    if language:
        snippets = [snippet for snippet in snippets if snippet.language == language]
    return render_template("search.html", snippets=snippets)


@app.errorhandler(404)
def not_found(e: Optional[Exception]) -> str:
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)