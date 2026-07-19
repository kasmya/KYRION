"""Code Snippet Manager with Flask, SQLAlchemy, Pygments, and Markdown."""
import os, logging
from flask import Flask, request, jsonify, render_template_string
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
engine = create_engine("sqlite:///snippets.db")
Base = declarative_base()
Session = sessionmaker(bind=engine)

class Snippet(Base):
    __tablename__ = "snippets"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    code = Column(Text, nullable=False)
    language = Column(String, default="text")
    tags = Column(String) # Comma-separated
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Snippet Manager</title>
    <style>{{ css | safe }}</style>
</head>
<body>
    <h1>Code Snippets</h1>
    <form action="/add" method="post">
        <input type="text" name="title" placeholder="Title" required><br>
        <textarea name="code" placeholder="Code" required></textarea><br>
        <input type="text" name="language" placeholder="Language (e.g., python)"><br>
        <input type="text" name="tags" placeholder="Tags (comma-separated)"><br>
        <button type="submit">Save</button>
    </form>
    <hr>
    {% for s in snippets %}
        <h2>{{ s.title }} <small>({{ s.language }})</small></h2>
        <p>Tags: {{ s.tags }}</p>
        <div>{{ s.highlighted | safe }}</div>
        <a href="/delete/{{ s.id }}">Delete</a>
        <hr>
    {% endfor %}
</body>
</html>
"""

def highlight_code(code: str, language: str) -> str:
    """Apply syntax highlighting using Pygments."""
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except:
        lexer = TextLexer()
    formatter = HtmlFormatter(style='monokai', linenos=True, cssclass="code-highlight")
    return highlight(code, lexer, formatter)

@app.route('/')
def index():
    session = Session()
    snippets = session.query(Snippet).all()
    data = []
    for s in snippets:
        data.append({
            "title": s.title,
            "language": s.language,
            "tags": s.tags,
            "highlighted": highlight_code(s.code, s.language)
        })
    session.close()
    
    css = HtmlFormatter(style='monokai').get_style_defs('.code-highlight')
    return render_template_string(HTML_TEMPLATE, snippets=data, css=css)

@app.route('/add', methods=['POST'])
def add_snippet():
    title = request.form.get('title')
    code = request.form.get('code')
    language = request.form.get('language', 'text')
    tags = request.form.get('tags', '')
    
    if not title or not code:
        return jsonify({"error": "Title and code required"}), 400
        
    session = Session()
    snippet = Snippet(title=title, code=code, language=language, tags=tags)
    session.add(snippet)
    session.commit()
    session.close()
    return jsonify({"message": "Saved"}), 201

@app.route('/delete/<int:id>')
def delete_snippet(id: int):
    session = Session()
    session.query(Snippet).filter_by(id=id).delete()
    session.commit()
    session.close()
    return jsonify({"message": "Deleted"}), 200

@app.route('/export/<format>')
def export_snippets(format: str):
    session = Session()
    snippets = session.query(Snippet).all()
    session.close()
    
    if format == 'md':
        content = "\n\n".join([f"# {s.title}\n```{s.language}\n{s.code}\n```" for s in snippets])
        return content, 200, {'Content-Type': 'text/markdown'}
    elif format == 'html':
        content = "<br>".join([f"<h2>{s.title}</h2>{highlight_code(s.code, s.language)}" for s in snippets])
        return content, 200, {'Content-Type': 'text/html'}
    return jsonify({"error": "Invalid format"}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)