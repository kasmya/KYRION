from typing import List, Dict
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import html

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///snippets.db'
db = SQLAlchemy(app)

class Snippet(db.Model):
    """Represents a code snippet."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(200), nullable=False)
    code = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"Snippet('{self.title}', '{self.language}')"

    def to_dict(self) -> Dict:
        """Returns a dictionary representation of the snippet."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'language': self.language,
            'tags': self.tags.split(','),
            'code': self.code
        }

def create_snippet(title: str, description: str, language: str, tags: str, code: str) -> Snippet:
    """Creates a new snippet."""
    snippet = Snippet(title=title, description=description, language=language, tags=tags, code=code)
    db.session.add(snippet)
    db.session.commit()
    return snippet

def get_snippets() -> List[Snippet]:
    """Returns a list of all snippets."""
    return Snippet.query.all()

def get_snippet(id: int) -> Snippet:
    """Returns a snippet by ID."""
    return Snippet.query.get(id)

def search_snippets(keyword: str, language: str = None) -> List[Snippet]:
    """Searches for snippets by keyword and language."""
    if language:
        return Snippet.query.filter(Snippet.title.like(f'%{keyword}%') | Snippet.description.like(f'%{keyword}%') | Snippet.tags.like(f'%{keyword}%')).filter_by(language=language).all()
    else:
        return Snippet.query.filter(Snippet.title.like(f'%{keyword}%') | Snippet.description.like(f'%{keyword}%') | Snippet.tags.like(f'%{keyword}%')).all()

def edit_snippet(id: int, title: str, description: str, language: str, tags: str, code: str) -> Snippet:
    """Edits a snippet."""
    snippet = get_snippet(id)
    if snippet:
        snippet.title = title
        snippet.description = description
        snippet.language = language
        snippet.tags = tags
        snippet.code = code
        db.session.commit()
        return snippet
    else:
        raise ValueError("Snippet not found")

def delete_snippet(id: int) -> None:
    """Deletes a snippet."""
    snippet = get_snippet(id)
    if snippet:
        db.session.delete(snippet)
        db.session.commit()
    else:
        raise ValueError("Snippet not found")

def syntax_highlight(code: str, language: str) -> str:
    """Syntax highlights the code."""
    lexer = get_lexer_by_name(language)
    formatter = HtmlFormatter()
    return highlight(code, lexer, formatter)

@app.route('/snippets', methods=['POST'])
def create_snippet_endpoint():
    """Creates a new snippet."""
    try:
        data = request.json
        title = data['title']
        description = data['description']
        language = data['language']
        tags = data['tags']
        code = data['code']
        snippet = create_snippet(title, description, language, tags, code)
        return jsonify(snippet.to_dict())
    except KeyError as e:
        return jsonify({'error': f'Missing field: {e}'}), 400

@app.route('/snippets', methods=['GET'])
def get_snippets_endpoint():
    """Returns a list of all snippets."""
    try:
        snippets = get_snippets()
        return jsonify([snippet.to_dict() for snippet in snippets])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/snippets/<int:id>', methods=['GET'])
def get_snippet_endpoint(id: int):
    """Returns a snippet by ID."""
    try:
        snippet = get_snippet(id)
        if snippet:
            return jsonify(snippet.to_dict())
        else:
            return jsonify({'error': 'Snippet not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/snippets/search', methods=['GET'])
def search_snippets_endpoint():
    """Searches for snippets by keyword and language."""
    try:
        keyword = request.args.get('keyword')
        language = request.args.get('language')
        snippets = search_snippets(keyword, language)
        return jsonify([snippet.to_dict() for snippet in snippets])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/snippets/<int:id>', methods=['PUT'])
def edit_snippet_endpoint(id: int):
    """Edits a snippet."""
    try:
        data = request.json
        title = data['title']
        description = data['description']
        language = data['language']
        tags = data['tags']
        code = data['code']
        snippet = edit_snippet(id, title, description, language, tags, code)
        return jsonify(snippet.to_dict())
    except KeyError as e:
        return jsonify({'error': f'Missing field: {e}'}), 400

@app.route('/snippets/<int:id>', methods=['DELETE'])
def delete_snippet_endpoint(id: int):
    """Deletes a snippet."""
    try:
        delete_snippet(id)
        return jsonify({'message': 'Snippet deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/snippets/<int:id>/highlight', methods=['GET'])
def syntax_highlight_endpoint(id: int):
    """Syntax highlights the code."""
    try:
        snippet = get_snippet(id)
        if snippet:
            highlighted_code = syntax_highlight(snippet.code, snippet.language)
            return jsonify({'highlighted_code': highlighted_code})
        else:
            return jsonify({'error': 'Snippet not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)