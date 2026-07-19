"""
Code Snippet Manager with syntax highlighting and export capabilities.

Features:
- Create, edit, delete snippets (title, code, tags)
- Syntax highlighting with Pygments
- Search by tag or content
- Export snippets (Markdown, HTML)
- Code language detection
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import re

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_, func
import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, get_all_lexers
from pygments.formatters import HtmlFormatter, TerminalFormatter
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('snippet_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///snippets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

class Snippet(db.Model):
    """Code snippet model."""
    __tablename__ = 'snippets'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), default='text')
    description = db.Column(db.Text)
    tags = db.Column(db.String(500))  # Comma-separated tags
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    view_count = db.Column(db.Integer, default=0)
    
    def get_tags(self) -> List[str]:
        """Get tags as list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
    
    def set_tags(self, tags: List[str]) -> None:
        """Set tags from list."""
        self.tags = ','.join(tags)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'code': self.code,
            'language': self.language,
            'description': self.description,
            'tags': self.get_tags(),
            'is_public': self.is_public,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'view_count': self.view_count
        }
    
    def __repr__(self) -> str:
        return f'<Snippet {self.title}>'

class SyntaxHighlighter:
    """Handles syntax highlighting with Pygments."""
    
    # Common language mappings
    LANGUAGE_ALIASES = {
        'js': 'javascript',
        'ts': 'typescript',
        'py': 'python',
        'rb': 'ruby',
        'sh': 'bash',
        'yml': 'yaml',
        'md': 'markdown',
        'txt': 'text',
    }
    
    @classmethod
    def get_available_languages(cls) -> List[Dict[str, str]]:
        """Get list of available languages."""
        languages = []
        for lexer in get_all_lexers():
            if lexer[1]:
                languages.append({
                    'name': lexer[0],
                    'aliases': lexer[1][:5]  # First 5 aliases
                })
        return sorted(languages, key=lambda x: x['name'])
    
    @classmethod
    def normalize_language(cls, language: str) -> str:
        """
        Normalize language name.
        
        Args:
            language: Language name or alias
            
        Returns:
            Normalized language name
        """
        language = language.lower().strip()
        
        # Check aliases
        if language in cls.LANGUAGE_ALIASES:
            return cls.LANGUAGE_ALIASES[language]
        
        # Try to find matching lexer
        try:
            lexer = get_lexer_by_name(language)
            return lexer.name.lower()
        except ClassNotFound:
            pass
        
        return language
    
    @classmethod
    def detect_language(cls, code: str) -> str:
        """
        Detect programming language from code.
        
        Args:
            code: Source code
            
        Returns:
            Detected language name
        """
        try:
            lexer = guess_lexer(code)
            return lexer.name.lower()
        except:
            return 'text'
    
    @classmethod
    def highlight_code(
        cls,
        code: str,
        language: str = 'text',
        style: str = 'monokai',
        linenos: bool = True,
        cssclass: str = 'highlight'
    ) -> str:
        """
        Highlight code with Pygments.
        
        Args:
            code: Source code
            language: Programming language
            style: Pygments style name
            linenos: Show line numbers
            cssclass: CSS class for wrapper
            
        Returns:
            HTML string with syntax highlighting
        """
        try:
            language = cls.normalize_language(language)
            lexer = get_lexer_by_name(language, stripall=True)
        except ClassNotFound:
            lexer = get_lexer_by_name('text', stripall=True)
        
        formatter = HtmlFormatter(
            style=style,
            linenos='table' if linenos else False,
            cssclass=cssclass,
            full=True
        )
        
        highlighted = highlight(code, lexer, formatter)
        
        return highlighted
    
    @classmethod
    def get_pygments_css(cls, style: str = 'monokai') -> str:
        """
        Get CSS for Pygments style.
        
        Args:
            style: Style name
            
        Returns:
            CSS string
        """
        formatter = HtmlFormatter(style=style)
        return formatter.get_style_defs('.highlight')

class SnippetExporter:
    """Handles exporting snippets in various formats."""
    
    @staticmethod
    def export_to_markdown(snippet: Snippet) -> str:
        """
        Export snippet as Markdown.
        
        Args:
            snippet: Snippet object
            
        Returns:
            Markdown string
        """
        md = f"# {snippet.title}\n\n"
        
        if snippet.description:
            md += f"{snippet.description}\n\n"
        
        md += f"**Language:** {snippet.language}\n\n"
        
        if snippet.tags:
            tags = snippet.get_tags()
            md += f"**Tags:** {' '.join(f'`{tag}`' for tag in tags)}\n\n"
        
        md += f"**Created:** {snippet.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        md += f"**Updated:** {snippet.updated_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        
        md += f"```{snippet.language}\n{snippet.code}\n```\n"
        
        return md
    
    @staticmethod
    def export_to_html(snippet: Snippet, style: str = 'monokai') -> str:
        """
        Export snippet as HTML.
        
        Args:
            snippet: Snippet object
            style: Highlighting style
            
        Returns:
            HTML string
        """
        highlighter = SyntaxHighlighter()
        highlighted_code = highlighter.highlight_code(
            snippet.code, snippet.language, style
        )
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{snippet.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; }}
        .snippet-header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 20px; }}
        .snippet-title {{ color: #333; }}
        .snippet-meta {{ color: #666; font-size: 0.9em; }}
        .tag {{ display: inline-block; background: #f0f0f0; padding: 2px 8px; margin: 2px; border-radius: 3px; font-size: 0.85em; }}
        .description {{ background: #f9f9f9; padding: 15px; border-left: 4px solid #007bff; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="snippet-header">
        <h1 class="snippet-title">{snippet.title}</h1>
        <div class="snippet-meta">
            <span>Language: <strong>{snippet.language}</strong></span> |
            <span>Created: {snippet.created_at.strftime('%Y-%m-%d')}</span>
        </div>
        <div>
            {''.join(f'<span class="tag">{tag}</span>' for tag in snippet.get_tags())}
        </div>
    </div>
    
    {f'<div class="description">{snippet.description}</div>' if snippet.description else ''}
    
    {highlighted_code}
</body>
</html>"""
        
        return html
    
    @staticmethod
    def export_batch_markdown(snippets: List[Snippet], filename: str = "snippets.md") -> str:
        """
        Export multiple snippets as single Markdown file.
        
        Args:
            snippets: List of snippets
            filename: Output filename
            
        Returns:
            Combined Markdown string
        """
        md = "# Code Snippets Collection\n\n"
        md += f"*Exported on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        md += "---\n\n"
        
        for i, snippet in enumerate(snippets, 1):
            md += f"## {i}. {snippet.title}\n\n"
            
            if snippet.description:
                md += f"{snippet.description}\n\n"
            
            md += f"**Language:** {snippet.language} | "
            md += f"**Tags:** {', '.join(snippet.get_tags())}\n\n"
            
            md += f"```{snippet.language}\n{snippet.code}\n```\n\n"
            
            if i < len(snippets):
                md += "---\n\n"
        
        return md

# Routes
@app.route('/')
def index():
    """Home page - list all public snippets."""
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    query = Snippet.query.filter_by(is_public=True)
    
    # Search
    search = request.args.get('search', '')
    if search:
        query = query.filter(
            or_(
                Snippet.title.ilike(f'%{search}%'),
                Snippet.code.ilike(f'%{search}%'),
                Snippet.description.ilike(f'%{search}%'),
                Snippet.tags.ilike(f'%{search}%')
            )
        )
    
    # Filter by language
    language = request.args.get('language', '')
    if language:
        query = query.filter(Snippet.language == language)
    
    # Filter by tag
    tag = request.args.get('tag', '')
    if tag:
        query = query.filter(Snippet.tags.ilike(f'%{tag}%'))
    
    snippets = query.order_by(Snippet.updated_at.desc()).paginate(
        page=page, per_page=per_page
    )
    
    # Get all languages and tags for filters
    languages = db.session.query(Snippet.language).distinct().all()
    all_tags = set()
    for snippet in Snippet.query.all():
        all_tags.update(snippet.get_tags())
    
    return render_template(
        'index.html',
        snippets=snippets,
        languages=[l[0] for l in languages],
        tags=sorted(all_tags),
        search=search,
        current_language=language,
        current_tag=tag
    )

@app.route('/snippet/<int:snippet_id>')
def view_snippet(snippet_id: int):
    """View a single snippet."""
    snippet = Snippet.query.get_or_404(snippet_id)
    
    # Increment view count
    snippet.view_count += 1
    db.session.commit()
    
    # Highlight code
    highlighter = SyntaxHighlighter()
    highlighted_code = highlighter.highlight_code(
        snippet.code, snippet.language, linenos=True
    )
    
    return render_template(
        'view.html',
        snippet=snippet,
        highlighted_code=highlighted_code
    )

@app.route('/snippet/create', methods=['GET', 'POST'])
def create_snippet():
    """Create a new snippet."""
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            code = request.form.get('code', '').strip()
            language = request.form.get('language', 'text').strip().lower()
            description = request.form.get('description', '').strip()
            tags = request.form.get('tags', '').strip()
            is_public = request.form.get('is_public') == 'on'
            
            if not title or not code:
                flash('Title and code are required', 'danger')
                return render_template('create.html')
            
            # Auto-detect language if not specified
            if language == 'auto' or not language:
                language = SyntaxHighlighter.detect_language(code)
            
            snippet = Snippet(
                title=title,
                code=code,
                language=language,
                description=description,
                is_public=is_public
            )
            snippet.set_tags([t.strip() for t in tags.split(',') if t.strip()])
            
            db.session.add(snippet)
            db.session.commit()
            
            logger.info(f"Snippet created: {snippet.title} (ID: {snippet.id})")
            flash('Snippet created successfully!', 'success')
            return redirect(url_for('view_snippet', snippet_id=snippet.id))
            
        except Exception as e:
            logger.error(f"Error creating snippet: {str(e)}", exc_info=True)
            flash('Error creating snippet', 'danger')
            db.session.rollback()
    
    languages = SyntaxHighlighter.get_available_languages()
    return render_template('create.html', languages=languages[:50])

@app.route('/snippet/<int:snippet_id>/edit', methods=['GET', 'POST'])
def edit_snippet(snippet_id: int):
    """Edit an existing snippet."""
    snippet = Snippet.query.get_or_404(snippet_id)
    
    if request.method == 'POST':
        try:
            snippet.title = request.form.get('title', '').strip()
            snippet.code = request.form.get('code', '').strip()
            snippet.language = request.form.get('language', 'text').strip().lower()
            snippet.description = request.form.get('description', '').strip()
            snippet.is_public = request.form.get('is_public') == 'on'
            
            tags = request.form.get('tags', '').strip()
            snippet.set_tags([t.strip() for t in tags.split(',') if t.strip()])
            
            db.session.commit()
            
            logger.info(f"Snippet updated: {snippet.id}")
            flash('Snippet updated successfully!', 'success')
            return redirect(url_for('view_snippet', snippet_id=snippet.id))
            
        except Exception as e:
            logger.error(f"Error updating snippet: {str(e)}", exc_info=True)
            flash('Error updating snippet', 'danger')
            db.session.rollback()
    
    languages = SyntaxHighlighter.get_available_languages()
    return render_template(
        'edit.html',
        snippet=snippet,
        languages=languages[:50]
    )

@app.route('/snippet/<int:snippet_id>/delete', methods=['POST'])
def delete_snippet(snippet_id: int):
    """Delete a snippet."""
    snippet = Snippet.query.get_or_404(snippet_id)
    
    try:
        db.session.delete(snippet)
        db.session.commit()
        logger.info(f"Snippet deleted: {snippet_id}")
        flash('Snippet deleted', 'info')
    except Exception as e:
        logger.error(f"Error deleting snippet: {str(e)}")
        flash('Error deleting snippet', 'danger')
        db.session.rollback()
    
    return redirect(url_for('index'))

@app.route('/snippet/<int:snippet_id>/export/<format>')
def export_snippet(snippet_id: int, format: str):
    """Export snippet in specified format."""
    snippet = Snippet.query.get_or_404(snippet_id)
    
    exporter = SnippetExporter()
    
    if format == 'markdown':
        content = exporter.export_to_markdown(snippet)
        filename = f"{snippet.title.lower().replace(' ', '_')}.md"
        mimetype = 'text/markdown'
    
    elif format == 'html':
        content = exporter.export_to_html(snippet)
        filename = f"{snippet.title.lower().replace(' ', '_')}.html"
        mimetype = 'text/html'
    
    else:
        abort(400, description="Unsupported export format")
    
    from io import BytesIO
    buffer = BytesIO(content.encode('utf-8'))
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )

@app.route('/export/all/<format>')
def export_all_snippets(format: str):
    """Export all snippets in specified format."""
    snippets = Snippet.query.filter_by(is_public=True).all()
    
    exporter = SnippetExporter()
    
    if format == 'markdown':
        content = exporter.export_batch_markdown(snippets)
        filename = "all_snippets.md"
        mimetype = 'text/markdown'
    else:
        abort(400, description="Unsupported export format")
    
    from io import BytesIO
    buffer = BytesIO(content.encode('utf-8'))
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/snippets')
def api_get_snippets():
    """API endpoint to get snippets."""
    snippets = Snippet.query.filter_by(is_public=True).all()
    return jsonify([s.to_dict() for s in snippets])

@app.route('/api/snippets/search')
def api_search_snippets():
    """API endpoint to search snippets."""
    query = request.args.get('q', '')
    language = request.args.get('language', '')
    tag = request.args.get('tag', '')
    
    q = Snippet.query.filter_by(is_public=True)
    
    if query:
        q = q.filter(
            or_(
                Snippet.title.ilike(f'%{query}%'),
                Snippet.code.ilike(f'%{query}%'),
                Snippet.description.ilike(f'%{query}%'),
                Snippet.tags.ilike(f'%{query}%')
            )
        )
    
    if language:
        q = q.filter(Snippet.language == language)
    
    if tag:
        q = q.filter(Snippet.tags.ilike(f'%{tag}%'))
    
    snippets = q.limit(50).all()
    return jsonify([s.to_dict() for s in snippets])

@app.route('/api/languages')
def api_get_languages():
    """API endpoint to get available languages."""
    languages = db.session.query(Snippet.language, func.count(Snippet.id)).\
        group_by(Snippet.language).all()
    return jsonify([{'name': l[0], 'count': l[1]} for l in languages])

@app.route('/api/tags')
def api_get_tags():
    """API endpoint to get all tags."""
    tags_count = {}
    for snippet in Snippet.query.all():
        for tag in snippet.get_tags():
            tags_count[tag] = tags_count.get(tag, 0) + 1
    
    return jsonify([{'name': k, 'count': v} for k, v in sorted(tags_count.items())])

@app.route('/api/detect-language', methods=['POST'])
def api_detect_language():
    """API endpoint to detect code language."""
    data = request.get_json()
    code = data.get('code', '')
    
    if not code:
        return jsonify({'error': 'No code provided'}), 400
    
    language = SyntaxHighlighter.detect_language(code)
    return jsonify({'language': language})

# HTML Templates
TEMPLATES = {
    'base.html': '''
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}Code Snippet Manager{% endblock %}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1e1e1e; color: #d4d4d4; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        nav { background: #2d2d2d; padding: 15px 20px; margin-bottom: 20px; border-radius: 8px; display: flex; justify-content: space-between; }
        nav a { color: #4ec9b0; text-decoration: none; margin-right: 15px; }
        nav a:hover { color: #569cd6; }
        .snippet-card { background: #2d2d2d; border: 1px solid #3e3e3e; border-radius: 8px; padding: 20px; margin: 10px 0; }
        .snippet-card:hover { border-color: #4ec9b0; }
        .tag { display: inline-block; background: #3e3e3e; color: #4ec9b0; padding: 2px 8px; margin: 2px; border-radius: 3px; font-size: 0.85em; }
        .language-badge { display: inline-block; background: #569cd6; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.85em; }
        input, textarea, select { background: #3c3c3c; color: #d4d4d4; border: 1px solid #3e3e3e; padding: 10px; border-radius: 4px; width: 100%; margin: 5px 0; }
        button, .btn { background: #4ec9b0; color: #1e1e1e; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        button:hover { background: #569cd6; }
        .search-bar { display: flex; gap: 10px; margin: 20px 0; }
        .search-bar input { flex: 1; }
        pre { background: #1e1e1e; padding: 15px; border-radius: 4px; overflow-x: auto; }
        code { font-family: 'Consolas', 'Monaco', monospace; }
        .highlight { border-radius: 4px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        .meta { color: #858585; font-size: 0.9em; }
    </style>
</head>
<body>
    <nav>
        <div>
            <a href="/">Snippets</a>
            <a href="/snippet/create">New Snippet</a>
        </div>
        <div>
            <a href="/export/all/markdown">Export All</a>
        </div>
    </nav>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
''',
    'index.html': '''
{% extends "base.html" %}
{% block content %}
<h1>Code Snippets</h1>
<div class="search-bar">
    <input type="text" id="search" placeholder="Search snippets..." value="{{ search }}">
    <select id="languageFilter">
        <option value="">All Languages</option>
        {% for lang in languages %}
        <option value="{{ lang }}" {% if current_language == lang %}selected{% endif %}>{{ lang }}</option>
        {% endfor %}
    </select>
    <button onclick="applyFilters()">Search</button>
</div>
<div class="grid">
    {% for snippet in snippets.items %}
    <div class="snippet-card">
        <h3><a href="/snippet/{{ snippet.id }}">{{ snippet.title }}</a></h3>
        <span class="language-badge">{{ snippet.language }}</span>
        <p class="meta">Views: {{ snippet.view_count }} | Updated: {{ snippet.updated_at.strftime('%Y-%m-%d') }}</p>
        <div>
            {% for tag in snippet.get_tags() %}
            <span class="tag">{{ tag }}</span>
            {% endfor %}
        </div>
        {% if snippet.description %}
        <p>{{ snippet.description[:100] }}{% if snippet.description|length > 100 %}...{% endif %}</p>
        {% endif %}
        <pre><code>{{ snippet.code[:200] }}{% if snippet.code|length > 200 %}...{% endif %}</code></pre>
    </div>
    {% endfor %}
</div>
{% if snippets.pages > 1 %}
<div style="text-align: center; margin: 20px 0;">
    {% for page in range(1, snippets.pages + 1) %}
    <a href="?page={{ page }}{% if search %}&search={{ search }}{% endif %}" 
       style="padding: 5px 10px; {% if page == snippets.page %}background: #4ec9b0;{% endif %}">
        {{ page }}
    </a>
    {% endfor %}
</div>
{% endif %}
<script>
function applyFilters() {
    const search = document.getElementById('search').value;
    const language = document.getElementById('languageFilter').value;
    window.location.href = `/?search=${search}&language=${language}`;
}
</script>
{% endblock %}
''',
    'view.html': '''
{% extends "base.html" %}
{% block title %}{{ snippet.title }}{% endblock %}
{% block content %}
<h1>{{ snippet.title }}</h1>
<p><span class="language-badge">{{ snippet.language }}</span></p>
<div>
    {% for tag in snippet.get_tags() %}
    <span class="tag">{{ tag }}</span>
    {% endfor %}
</div>
<p class="meta">Created: {{ snippet.created_at.strftime('%Y-%m-%d %H:%M') }} | Views: {{ snippet.view_count }}</p>
{% if snippet.description %}
<div style="background: #2d2d2d; padding: 15px; margin: 15px 0; border-left: 4px solid #4ec9b0;">
    {{ snippet.description }}
</div>
{% endif %}
{{ highlighted_code | safe }}
<div style="margin: 20px 0;">
    <a href="/snippet/{{ snippet.id }}/edit" class="btn">Edit</a>
    <a href="/snippet/{{ snippet.id }}/export/markdown" class="btn">Export MD</a>
    <a href="/snippet/{{ snippet.id }}/export/html" class="btn">Export HTML</a>
    <form action="/snippet/{{ snippet.id }}/delete" method="POST" style="display:inline;">
        <button type="submit" onclick="return confirm('Delete this snippet?')">Delete</button>
    </form>
</div>
{% endblock %}
''',
    'create.html': '''
{% extends "base.html" %}
{% block content %}
<h1>Create Snippet</h1>
<form method="POST">
    <input type="text" name="title" placeholder="Snippet Title" required>
    <select name="language">
        <option value="auto">Auto-detect</option>
        {% for lang in languages %}
        <option value="{{ lang.aliases[0] if lang.aliases else lang.name.lower() }}">{{ lang.name }}</option>
        {% endfor %}
    </select>
    <textarea name="code" rows="15" placeholder="Paste your code here..." required></textarea>
    <textarea name="description" rows="3" placeholder="Description (optional)"></textarea>
    <input type="text" name="tags" placeholder="Tags (comma-separated)">
    <label><input type="checkbox" name="is_public" checked> Public</label><br>
    <button type="submit">Create Snippet</button>
</form>
{% endblock %}
''',
    'edit.html': '''
{% extends "base.html" %}
{% block content %}
<h1>Edit Snippet</h1>
<form method="POST">
    <input type="text" name="title" value="{{ snippet.title }}" required>
    <select name="language">
        {% for lang in languages %}
        <option value="{{ lang.aliases[0] if lang.aliases else lang.name.lower() }}"
                {% if lang.name.lower() == snippet.language %}selected{% endif %}>
            {{ lang.name }}
        </option>
        {% endfor %}
    </select>
    <textarea name="code" rows="15" required>{{ snippet.code }}</textarea>
    <textarea name="description" rows="3">{{ snippet.description or '' }}</textarea>
    <input type="text" name="tags" value="{{ ','.join(snippet.get_tags()) }}">
    <label><input type="checkbox" name="is_public" {% if snippet.is_public %}checked{% endif %}> Public</label><br>
    <button type="submit">Update Snippet</button>
</form>
{% endblock %}
'''
}

def create_templates():
    """Create template files."""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    for filename, content in TEMPLATES.items():
        with open(os.path.join(templates_dir, filename), 'w') as f:
            f.write(content)

if __name__ == '__main__':
    create_templates()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5003)
