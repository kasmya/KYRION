from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
from typing import Dict, List, Optional

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class User(db.Model):
    """User Model."""
    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password: str = db.Column(db.String(120), nullable=False)
    posts: List['Post'] = db.relationship('Post', backref='author', lazy=True)
    comments: List['Comment'] = db.relationship('Comment', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

    def set_password(self, password: str) -> None:
        """Set user password."""
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Check user password."""
        return bcrypt.check_password_hash(self.password, password)


class Post(db.Model):
    """Post Model."""
    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(100), nullable=False)
    content: str = db.Column(db.Text, nullable=False)
    date_posted: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id: int = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments: List['Comment'] = db.relationship('Comment', backref='post', lazy=True)
    upvotes: int = db.Column(db.Integer, default=0)
    downvotes: int = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"


class Comment(db.Model):
    """Comment Model."""
    id: int = db.Column(db.Integer, primary_key=True)
    content: str = db.Column(db.Text, nullable=False)
    date_posted: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id: int = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self):
        return f"Comment('{self.date_posted}')"


@app.before_request
def before_request():
    """Set current user before request."""
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])
    else:
        g.user = None


@app.route('/register', methods=['POST'])
def register() -> str:
    """Register new user."""
    data: Dict[str, str] = request.get_json()
    if not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if user:
        return jsonify({'error': 'Username already exists'}), 400
    new_user = User(username=data['username'], email=data['email'])
    new_user.set_password(data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'New user created'}), 201


@app.route('/login', methods=['POST'])
def login() -> str:
    """Login user."""
    data: Dict[str, str] = request.get_json()
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = user.id
    return jsonify({'message': 'User logged in'}), 200


@app.route('/logout')
def logout() -> str:
    """Logout user."""
    session.pop('user_id', None)
    return jsonify({'message': 'User logged out'}), 200


@app.route('/posts', methods=['POST'])
def create_post() -> str:
    """Create new post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    data: Dict[str, str] = request.get_json()
    if not data.get('title') or not data.get('content'):
        return jsonify({'error': 'Missing required fields'}), 400
    new_post = Post(title=data['title'], content=data['content'], user_id=g.user.id)
    db.session.add(new_post)
    db.session.commit()
    return jsonify({'message': 'New post created'}), 201


@app.route('/posts/<int:post_id>', methods=['PUT'])
def edit_post(post_id: int) -> str:
    """Edit post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    post = Post.query.get(post_id)
    if not post or post.author != g.user:
        return jsonify({'error': 'Post not found or not yours'}), 404
    data: Dict[str, str] = request.get_json()
    if data.get('title'):
        post.title = data['title']
    if data.get('content'):
        post.content = data['content']
    db.session.commit()
    return jsonify({'message': 'Post updated'}), 200


@app.route('/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id: int) -> str:
    """Delete post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    post = Post.query.get(post_id)
    if not post or post.author != g.user:
        return jsonify({'error': 'Post not found or not yours'}), 404
    db.session.delete(post)
    db.session.commit()
    return jsonify({'message': 'Post deleted'}), 200


@app.route('/posts/<int:post_id>/comments', methods=['POST'])
def create_comment(post_id: int) -> str:
    """Create comment on post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    data: Dict[str, str] = request.get_json()
    if not data.get('content'):
        return jsonify({'error': 'Missing required fields'}), 400
    new_comment = Comment(content=data['content'], user_id=g.user.id, post_id=post_id)
    db.session.add(new_comment)
    db.session.commit()
    return jsonify({'message': 'New comment created'}), 201


@app.route('/posts/<int:post_id>/upvote', methods=['POST'])
def upvote_post(post_id: int) -> str:
    """Upvote post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    post.upvotes += 1
    db.session.commit()
    return jsonify({'message': 'Post upvoted'}), 200


@app.route('/posts/<int:post_id>/downvote', methods=['POST'])
def downvote_post(post_id: int) -> str:
    """Downvote post."""
    if not g.user:
        return jsonify({'error': 'You must be logged in'}), 401
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    post.downvotes += 1
    db.session.commit()
    return jsonify({'message': 'Post downvoted'}), 200


@app.route('/search', methods=['GET'])
def search_posts() -> str:
    """Search posts by title or content."""
    query: str = request.args.get('q')
    if not query:
        return jsonify({'error': 'Missing search query'}), 400
    posts = Post.query.filter(
        db.or_(
            Post.title.ilike(f'%{query}%'),
            Post.content.ilike(f'%{query}%')
        )
    ).all()
    return jsonify([{'id': p.id, 'title': p.title, 'content': p.content} for p in posts]), 200


if __name__ == '__main__':
    app.secret_key = 'secret'
    with app.app_context():
        db.create_all()
    app.run(debug=True)