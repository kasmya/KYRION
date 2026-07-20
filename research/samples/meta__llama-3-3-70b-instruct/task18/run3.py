from typing import List, Dict
from flask import Flask, request, jsonify
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import sqlite3
import json
import re

app = Flask(__name__)

# Database connection
conn = sqlite3.connect('snippets.db', check_same_thread=False)
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS snippets
             (id INTEGER PRIMARY KEY AUTOINCREMENT, title text, description text, language text, tags text, code text)''')
conn.commit()

# Close connection when app is closed
@app.teardown_appcontext
def close_connection(exception):
    conn.close()

def create_snippet(title: str, description: str, language: str, tags: List[str], code: str) -> int:
    """
    Create a new snippet.
    
    Args:
    title (str): The title of the snippet.
    description (str): The description of the snippet.
    language (str): The language of the snippet.
    tags (List[str]): The tags of the snippet.
    code (str): The code of the snippet.
    
    Returns:
    int: The ID of the newly created snippet.
    """
    c.execute("INSERT INTO snippets (title, description, language, tags, code) VALUES (?, ?, ?, ?, ?)",
              (title, description, language, json.dumps(tags), code))
    conn.commit()
    return c.lastrowid

def get_snippets() -> List[Dict]:
    """
    Get all snippets.
    
    Returns:
    List[Dict]: A list of dictionaries, each representing a snippet.
    """
    c.execute("SELECT * FROM snippets")
    rows = c.fetchall()
    snippets = []
    for row in rows:
        snippet = {
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'language': row[3],
            'tags': json.loads(row[4]),
            'code': row[5]
        }
        snippets.append(snippet)
    return snippets

def get_snippet(id: int) -> Dict:
    """
    Get a snippet by ID.
    
    Args:
    id (int): The ID of the snippet.
    
    Returns:
    Dict: A dictionary representing the snippet.
    """
    c.execute("SELECT * FROM snippets WHERE id=?", (id,))
    row = c.fetchone()
    if row is None:
        return None
    snippet = {
        'id': row[0],
        'title': row[1],
        'description': row[2],
        'language': row[3],
        'tags': json.loads(row[4]),
        'code': row[5]
    }
    return snippet

def search_snippets(keyword: str, language: str = None) -> List[Dict]:
    """
    Search snippets by keyword and language.
    
    Args:
    keyword (str): The keyword to search for.
    language (str): The language to search for (optional).
    
    Returns:
    List[Dict]: A list of dictionaries, each representing a matching snippet.
    """
    query = "SELECT * FROM snippets WHERE title LIKE ? OR description LIKE ?"
    params = ('%' + keyword + '%', '%' + keyword + '%')
    if language:
        query += " AND language=?"
        params = params + (language,)
    c.execute(query, params)
    rows = c.fetchall()
    snippets = []
    for row in rows:
        snippet = {
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'language': row[3],
            'tags': json.loads(row[4]),
            'code': row[5]
        }
        snippets.append(snippet)
    return snippets

def edit_snippet(id: int, title: str, description: str, language: str, tags: List[str], code: str) -> None:
    """
    Edit a snippet.
    
    Args:
    id (int): The ID of the snippet.
    title (str): The new title of the snippet.
    description (str): The new description of the snippet.
    language (str): The new language of the snippet.
    tags (List[str]): The new tags of the snippet.
    code (str): The new code of the snippet.
    """
    c.execute("UPDATE snippets SET title=?, description=?, language=?, tags=?, code=? WHERE id=?",
              (title, description, language, json.dumps(tags), code, id))
    conn.commit()

def delete_snippet(id: int) -> None:
    """
    Delete a snippet.
    
    Args:
    id (int): The ID of the snippet.
    """
    c.execute("DELETE FROM snippets WHERE id=?", (id,))
    conn.commit()

def highlight_code(code: str, language: str) -> str:
    """
    Highlight code with syntax highlighting.
    
    Args:
    code (str): The code to highlight.
    language (str): The language of the code.
    
    Returns:
    str: The highlighted code as HTML.
    """
    lexer = get_lexer_by_name(language)
    formatter = HtmlFormatter()
    return highlight(code, lexer, formatter)

@app.route('/snippets', methods=['GET'])
def get_all_snippets():
    snippets = get_snippets()
    return jsonify(snippets)

@app.route('/snippets/<int:id>', methods=['GET'])
def get_snippet(id: int):
    snippet = get_snippet(id)
    if snippet is None:
        return jsonify({'error': 'Snippet not found'}), 404
    return jsonify(snippet)

@app.route('/snippets', methods=['POST'])
def create_new_snippet():
    data = request.json
    if 'title' not in data or 'description' not in data or 'language' not in data or 'tags' not in data or 'code' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    title = data['title']
    description = data['description']
    language = data['language']
    tags = data['tags']
    code = data['code']
    id = create_snippet(title, description, language, tags, code)
    return jsonify({'id': id})

@app.route('/snippets/<int:id>', methods=['PUT'])
def edit_existing_snippet(id: int):
    data = request.json
    if 'title' not in data or 'description' not in data or 'language' not in data or 'tags' not in data or 'code' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    title = data['title']
    description = data['description']
    language = data['language']
    tags = data['tags']
    code = data['code']
    edit_snippet(id, title, description, language, tags, code)
    return jsonify({'message': 'Snippet updated successfully'})

@app.route('/snippets/<int:id>', methods=['DELETE'])
def delete_existing_snippet(id: int):
    delete_snippet(id)
    return jsonify({'message': 'Snippet deleted successfully'})

@app.route('/snippets/search', methods=['GET'])
def search_snippets():
    keyword = request.args.get('keyword')
    language = request.args.get('language')
    snippets = search_snippets(keyword, language)
    return jsonify(snippets)

@app.route('/snippets/<int:id>/highlight', methods=['GET'])
def highlight_snippet(id: int):
    snippet = get_snippet(id)
    if snippet is None:
        return jsonify({'error': 'Snippet not found'}), 404
    code = snippet['code']
    language = snippet['language']
    highlighted_code = highlight_code(code, language)
    return highlighted_code

if __name__ == '__main__':
    app.run(debug=True)