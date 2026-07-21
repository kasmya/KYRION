from flask import Flask, request, jsonify, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from werkzeug.exceptions import NotFound, Conflict, InternalServerError
from typing import Dict, List, Optional
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog_cms.db'
app.config['SECRET_KEY'] = 'your_secret_key_here'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)

class User(UserMixin, db.Model):
    """User Model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='comment_author', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storing."""
        return bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Check a stored password against one provided by user."""
        return bcrypt.check_password_hash(self.password, password)

class Post(db.Model):
    """Post Model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy=True)
    categories = db.relationship('Category', secondary='post_categories',
                                 backref=db.backref('posts', lazy=True))
    tags = db.relationship('Tag', secondary='post_tags',
                           backref=db.backref('posts', lazy=True))

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"

class Comment(db.Model):
    """Comment Model"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self):
        return f"Comment('{self.content}', '{self.date_posted}')"

class Category(db.Model):
    """Category Model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

    def __repr__(self):
        return f"Category('{self.name}')"

class Tag(db.Model):
    """Tag Model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

    def __repr__(self):
        return f"Tag('{self.name}')"

post_categories = db.Table('post_categories',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True))

post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True))

@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Load user from database for Flask-Login."""
    return User.query.get(int(user_id))

@app.before_request
def before_request():
    g.user = current_user

@app.route('/register', methods=['POST'])
def register():
    """Register a new user."""
    data: Dict[str, str] = request.get_json()
    if not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400

    new_user = User(username=data['username'], email=data['email'], password=User.hash_password(data['password']))
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'New user created'}), 201

@app.route('/login', methods=['POST'])
def login():
    """Login an existing user."""
    data: Dict[str, str] = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    if not user or not user.check_password(data.get('password')):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    login_user(user)
    return jsonify({'message': 'User logged in'}), 200

@app.route('/logout')
@login_required
def logout():
    """Logout the current user."""
    logout_user()
    return jsonify({'message': 'User logged out'}), 200

@app.route('/posts', methods=['GET', 'POST'])
@login_required
def manage_posts():
    """Create or read posts."""
    if request.method == 'POST':
        data: Dict[str, str] = request.get_json()
        if not data.get('title') or not data.get('content'):
            return jsonify({'error': 'Missing title or content'}), 400
        
        new_post = Post(title=data['title'], content=data['content'], author=current_user)
        
        # Handle categories
        if 'categories' in data:
            for cat_name in data['categories']:
                cat = Category.query.filter_by(name=cat_name).first()
                if not cat:
                    cat = Category(name=cat_name)
                    db.session.add(cat)
                    db.session.flush()  # To get the ID
                new_post.categories.append(cat)
        
        # Handle tags
        if 'tags' in data:
            for tag_name in data['tags']:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()  # To get the ID
                new_post.tags.append(tag)
        
        db.session.add(new_post)
        db.session.commit()
        return jsonify({'message': 'New post created'}), 201
    
    # GET all posts by current user
    posts = Post.query.filter_by(user_id=current_user.id).all()
    output = []
    for post in posts:
        post_data = {
            'id': post.id,
            'title': post.title,
            'content': post.content,
            'date_posted': post.date_posted,
            'categories': [cat.name for cat in post.categories],
            'tags': [tag.name for tag in post.tags]
        }
        output.append(post_data)
    return jsonify({'posts': output}), 200

@app.route('/posts/<int:post_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_post(post_id: int):
    """Read, update, or delete a specific post."""
    post = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found or not yours'}), 404
    
    if request.method == 'GET':
        post_data = {
            'id': post.id,
            'title': post.title,
            'content': post.content,
            'date_posted': post.date_posted,
            'categories': [cat.name for cat in post.categories],
            'tags': [tag.name for tag in post.tags],
            'comments': [{'id': c.id, 'content': c.content, 'date': c.date_posted} for c in post.comments]
        }
        return jsonify(post_data), 200
    
    elif request.method == 'PUT':
        data: Dict[str, str] = request.get_json()
        if 'title' in data:
            post.title = data['title']
        if 'content' in data:
            post.content = data['content']
        
        # Update categories
        if 'categories' in data:
            post.categories.clear()
            for cat_name in data['categories']:
                cat = Category.query.filter_by(name=cat_name).first()
                if not cat:
                    cat = Category(name=cat_name)
                    db.session.add(cat)
                    db.session.flush()  # To get the ID
                post.categories.append(cat)
        
        # Update tags
        if 'tags' in data:
            post.tags.clear()
            for tag_name in data['tags']:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()  # To get the ID
                post.tags.append(tag)
        
        db.session.commit()
        return jsonify({'message': 'Post updated'}), 200
    
    elif request.method == 'DELETE':
        db.session.delete(post)
        db.session.commit()
        return jsonify({'message': 'Post deleted'}), 200

@app.route('/posts/<int:post_id>/comments', methods=['POST',