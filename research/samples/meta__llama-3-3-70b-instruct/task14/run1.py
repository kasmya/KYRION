from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
db = SQLAlchemy(app)

class User(db.Model):
    """User model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def __init__(self, username: str, email: str, password: str):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check password"""
        return check_password_hash(self.password, password)

class Post(db.Model):
    """Post model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))

    def __init__(self, title: str, content: str, author_id: int):
        self.title = title
        self.content = content
        self.author_id = author_id

class Comment(db.Model):
    """Comment model"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    post = db.relationship('Post', backref=db.backref('comments', lazy=True))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('comments', lazy=True))

    def __init__(self, content: str, post_id: int, author_id: int):
        self.content = content
        self.post_id = post_id
        self.author_id = author_id

class Vote(db.Model):
    """Vote model"""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    post = db.relationship('Post', backref=db.backref('votes', lazy=True))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('votes', lazy=True))
    vote = db.Column(db.Boolean, nullable=False)

    def __init__(self, post_id: int, user_id: int, vote: bool):
        self.post_id = post_id
        self.user_id = user_id
        self.vote = vote

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register user"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists', 'error')
        else:
            user = User(username, email, password)
            db.session.add(user)
            db.session.commit()
            flash('User created successfully', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login user"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            flash('Logged in successfully', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/')
def index():
    """Index page"""
    posts = Post.query.all()
    return render_template('index.html', posts=posts)

@app.route('/post/<int:post_id>')
def post(post_id: int):
    """Post page"""
    post = Post.query.get(post_id)
    comments = Comment.query.filter_by(post_id=post_id).all()
    return render_template('post.html', post=post, comments=comments)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
def comment(post_id: int):
    """Comment on post"""
    content = request.form['content']
    comment = Comment(content, post_id, 1)  # Assuming user id is 1
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('post', post_id=post_id))

@app.route('/post/<int:post_id>/upvote')
def upvote(post_id: int):
    """Upvote post"""
    vote = Vote.query.filter_by(post_id=post_id, user_id=1).first()  # Assuming user id is 1
    if vote and vote.vote:
        flash('You have already upvoted this post', 'error')
    else:
        if vote:
            vote.vote = True
        else:
            vote = Vote(post_id, 1, True)  # Assuming user id is 1
            db.session.add(vote)
        db.session.commit()
    return redirect(url_for('post', post_id=post_id))

@app.route('/post/<int:post_id>/downvote')
def downvote(post_id: int):
    """Downvote post"""
    vote = Vote.query.filter_by(post_id=post_id, user_id=1).first()  # Assuming user id is 1
    if vote and not vote.vote:
        flash('You have already downvoted this post', 'error')
    else:
        if vote:
            vote.vote = False
        else:
            vote = Vote(post_id, 1, False)  # Assuming user id is 1
            db.session.add(vote)
        db.session.commit()
    return redirect(url_for('post', post_id=post_id))

@app.route('/search', methods=['POST'])
def search():
    """Search posts"""
    query = request.form['query']
    posts = Post.query.filter(Post.title.like(f'%{query}%')).all()
    return render_template('search.html', posts=posts)

if __name__ == '__main__':
    app.run(debug=True)