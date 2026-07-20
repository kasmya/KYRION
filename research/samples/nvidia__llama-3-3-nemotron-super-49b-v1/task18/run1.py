import os
import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from http import HTTPStatus
from functools import wraps
from flask import Flask, request, jsonify, abort, render_template_string
from flask import redirect, url_for
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'development')

# Database (Simplified for demo; use a real DB in production)
DATABASE: Dict[str, Dict] = {}

class Language(Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    # Add more as needed

@dataclass
class Snippet:
    """Code Snippet with metadata"""
    title: str
    description: str
    language: Language
    tags: List[str]
    code: str
    hashed_id: str = ""  # Auto-generated

    def __post_init__(self):
        self.hashed_id = sha256(f"{self.title}{self.description}".encode()).hexdigest()[:8]

def require_auth(f):
    """Simplified auth check for demo (Implement proper auth in production)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not app.config.get('AUTH_ENABLED', False) or request.headers.get('Auth-Token', '') == 'demo-token':
            return f(*args, **kwargs)
        abort(HTTPStatus.UNAUTHORIZED)
    return decorated_function

# Template for snippet display with syntax highlighting
TEMPLATE = """
<html>
<head>
    <style>{{ css|% safe }}</style>
</head>
<body>
<pre><code class="{{ language }}">{{ snippet }}</code></pre>
</body>
</html>
"""

@app.route('/snippets', methods=['GET'])
@require_auth
def list_snippets():
    """List all snippets with filtering"""
    query = request.args.get('query', '')
    language_filter = request.args.get('language', '')
    snippets = list(DATABASE.values())
    
    if query:
        snippets = [s for s in snippets if query.lower() in s.title.lower() or query.lower() in s.description.lower()]
    if language_filter and language_filter.upper() in [lang.value for lang in Language]:
        snippets = [s for s in snippets if s.language.value == language_filter.lower()]
    
    return jsonify([{
        'id': s.hashed_id,
        'title': s.title,
        'description': s.description,
        'language': s.language.value,
        'tags': s.tags
    } for s in snippets])

@app.route('/snippets/<snippet_id>', methods=['GET'])
@require_auth
def view_snippet(snippet_id: str):
    """View a snippet with syntax highlighting"""
    snippet = next((s for s in DATABASE.values() if s.hashed_id == snippet_id), None)
    if not snippet:
        abort(HTTPStatus.NOT_FOUND)
    
    try:
        lexer = get_lexer_by_name(snippet.language.value)
        css = HtmlFormatter().get_style_by_name('default').css_text
        highlighted = highlight(snippet.code, lexer, HtmlFormatter())
        return render_template_string(TEMPLATE, css=css, language=snippet.language.value, snippet=highlighted)
    except Exception as e:
        app.logger.error(f"Error highlighting {snippet_id}: {e}")
        return snippet.code, HTTPStatus.INTERNAL_SERVER_ERROR

@app.route('/snippets', methods=['POST'])
@require_auth
def create_snippet():
    """Create a new snippet"""
    data = request.get_json()
    if not data or not all(key in data for key in ['title', 'description', 'language', 'tags', 'code']):
        abort(HTTPStatus.BAD_REQUEST, "Missing required fields")
    
    try:
        language = Language[data['language'].upper()]
    except KeyError:
        abort(HTTPStatus.BAD_REQUEST, "Invalid language")
    
    snippet = Snippet(
        title=data['title'],
        description=data['description'],
        language=language,
        tags=data['tags'],
        code=data['code']
    )
    DATABASE[snippet.hashed_id] = snippet
    return jsonify({'id': snippet.hashed_id}), HTTPStatus.CREATED

@app.route('/snippets/<snippet_id>', methods=['PUT'])
@require_auth
def edit_snippet(snippet_id: str):
    """Edit an existing snippet"""
    snippet = next((s for s in DATABASE.values() if s.hashed_id == snippet_id), None)
    if not snippet:
        abort(HTTPStatus.NOT_FOUND)
    
    data = request.get_json()
    if data.get('title'): snippet.title = data['title']
    if data.get('description'): snippet.description = data['description']
    if data.get('language'):
        try:
            snippet.language = Language[data['language'].upper()]
        except KeyError:
            abort(HTTPStatus.BAD_REQUEST, "Invalid language")
    if data.get('tags'): snippet.tags = data['tags']
    if data.get('code'): snippet.code = data['code']
    return jsonify({'message': 'Snippet updated'}), HTTPStatus.OK

@app.route('/snippets/<snippet_id>', methods=['DELETE'])
@require_auth
def delete_snippet(snippet_id: str):
    """Delete a snippet"""
    if snippet_id in DATABASE:
        del DATABASE[snippet_id]
        return jsonify({'message': 'Snippet deleted'}), HTTPStatus.NO_CONTENT
    abort(HTTPStatus.NOT_FOUND)

if __name__ == '__main__':
    # For development only
    app.config['AUTH_ENABLED'] = False
    app.run(debug=True)