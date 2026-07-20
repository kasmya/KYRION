import json
import os
from typing import Dict, List, Optional
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# Snippet Data Structure (In-Memory for simplicity; consider a database for production)
snippets: Dict[str, Dict] = {}
snippet_id_counter: int = 0

# Template for Syntax Highlighting Display
TEMPLATE = """
<html><body>
<h1>{{ title }}</h1>
<p>{{ description }}</p>
<p>Language: {{ language }} | Tags: {{ tags|join(', ') }}</p>
<pre><code>{{ code|safe }}</code></pre>
</body></html>
"""

# Error Types
class SnippetError(Exception):
    pass

class SnippetNotFoundError(SnippetError):
    pass

# Utility Functions
def get_snippet(id: str) -> Dict:
    """Retrieve snippet by ID."""
    if id not in snippets:
        raise SnippetNotFoundError("Snippet not found")
    return snippets[id]

def sanitize_input(data: Dict) -> Dict:
    """Basic input sanitization (strip whitespace, enforce types)"""
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = value.strip()
        else:
            sanitized[key] = value
    return sanitized

def highlight_code(code: str, language: str) -> str:
    """Generate HTML with syntax highlighting."""
    try:
        lexer = get_lexer_by_name(language)
        formatter = HtmlFormatter()
        return highlight(code, lexer, formatter)
    except Exception as e:
        # Fallback to plain text on error
        return f"<pre><code>{code}</code></pre>"

# API Endpoints
@app.route('/snippets', methods=['POST'])
def create_snippet() -> str:
    """
    Create a new snippet.
    
    :body: title, description, language, tags (list), code
    :return: New snippet's ID
    """
    global snippet_id_counter
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    
    required_fields = ['title', 'description', 'language', 'tags', 'code']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        sanitized_data = sanitize_input(data)
        snippet_id = str(snippet_id_counter)
        snippet_id_counter += 1
        snippets[snippet_id] = {
            **sanitized_data,
            'tags': sanitized_data['tags']  # Ensure tags are properly handled
        }
        return jsonify({"id": snippet_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/snippets/<id>', methods=['GET'])
def view_snippet(id: str) -> str:
    """
    View a snippet with syntax highlighting.
    
    :param id: Snippet ID
    :return: HTML with highlighted code
    """
    try:
        snippet = get_snippet(id)
        highlighted_code = highlight_code(snippet['code'], snippet['language'])
        return render_template_string(TEMPLATE, **snippet, code=highlighted_code)
    except SnippetNotFoundError:
        return jsonify({"error": "Snippet not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/snippets/<id>', methods=['PUT'])
def update_snippet(id: str) -> str:
    """
    Update an existing snippet.
    
    :param id: Snippet ID
    :body: title, description, language, tags (list), code (any to update)
    :return: Success message
    """
    try:
        snippet = get_snippet(id)
        data = request.get_json() or {}
        sanitized_data = sanitize_input(data)
        for key, value in sanitized_data.items():
            if key in snippet:
                snippet[key] = value
        return "Snippet updated successfully", 200
    except SnippetNotFoundError:
        return jsonify({"error": "Snippet not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/snippets/<id>', methods=['DELETE'])
def delete_snippet(id: str) -> str:
    """
    Delete a snippet.
    
    :param id: Snippet ID
    :return: Success message
    """
    try:
        del snippets[id]
        return "Snippet deleted", 200
    except KeyError:
        return jsonify({"error": "Snippet not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search', methods=['GET'])
def search_snippets() -> str:
    """
    Search snippets by keyword or language.
    
    :query: keyword (string), language (string)
    :return: List of matching snippets
    """
    keyword = request.args.get('keyword')
    language = request.args.get('language')
    results = []
    for snippet in snippets.values():
        if (keyword and keyword.lower() in str(snippet).lower()) or \
           (language and snippet['language'].lower() == language.lower()):
            results.append(snippet)
    return jsonify(results), 200

if __name__ == '__main__':
    app.run(debug=True)