from flask import Flask, request, redirect, url_for, render_template, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
db = SQLAlchemy(app)

class User(db.Model):
    """Represents a user in the database."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    def __repr__(self):
        return f'User({self.username})'

    def set_password(self, password: str):
        """Sets the password for the user."""
        self.password = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Checks if the given password is correct."""
        return check_password_hash(self.password, password)

class Post(db.Model):
    """Represents a post in the database."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy=True)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'Post({self.title})'

class Comment(db.Model):
    """Represents a comment in the database."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'Comment({self.content})'

@app.route('/')
def index():
    """Renders the main page with a list of posts."""
    posts = Post.query.all()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registers a new user."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('User created successfully', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Logs in an existing user."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Logged in successfully', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs out the current user."""
    session.pop('user_id', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/post', methods=['GET', 'POST'])
def post():
    """Creates a new post."""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post = Post(title=title, content=content, user_id=session['user_id'])
        db.session.add(post)
        db.session.commit()
        flash('Post created successfully', 'success')
        return redirect(url_for('index'))
    return render_template('post.html')

@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id: int):
    """Views a post and its comments."""
    post = Post.query.get(post_id)
    if request.method == 'POST':
        content = request.form['content']
        comment = Comment(content=content, post_id=post_id, user_id=session['user_id'])
        db.session.add(comment)
        db.session.commit()
        flash('Comment added successfully', 'success')
    return render_template('view_post.html', post=post)

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id: int):
    """Edits a post."""
    post = Post.query.get(post_id)
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post.title = title
        post.content = content
        db.session.commit()
        flash('Post updated successfully', 'success')
        return redirect(url_for('view_post', post_id=post_id))
    return render_template('edit_post.html', post=post)

@app.route('/post/<int:post_id>/delete')
def delete_post(post_id: int):
    """Deletes a post."""
    post = Post.query.get(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted successfully', 'success')
    return redirect(url_for('index'))

@app.route('/post/<int:post_id>/upvote')
def upvote_post(post_id: int):
    """Upvotes a post."""
    post = Post.query.get(post_id)
    post.upvotes += 1
    db.session.commit()
    flash('Post upvoted successfully', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>/downvote')
def downvote_post(post_id: int):
    """Downvotes a post."""
    post = Post.query.get(post_id)
    post.downvotes += 1
    db.session.commit()
    flash('Post downvoted successfully', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/search', methods=['GET'])
def search():
    """Searches for posts."""
    query = request.args.get('q')
    posts = Post.query.filter(Post.title.like(f'%{query}%') | Post.content.like(f'%{query}%')).all()
    return render_template('search.html', posts=posts)

if __name__ == '__main__':
    app.run(debug=True)