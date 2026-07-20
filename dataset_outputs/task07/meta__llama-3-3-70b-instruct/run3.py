from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    """Represents a user in the database."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password: str) -> None:
        """Sets the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Checks the user's password."""
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    """Represents a blog post in the database."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))
    category = db.Column(db.String(64), nullable=False)
    tags = db.Column(db.String(128), nullable=False)

class Comment(db.Model):
    """Represents a comment in the database."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    post = db.relationship('Post', backref=db.backref('comments', lazy=True))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('comments', lazy=True))

login_manager = LoginManager(app)

@login_manager.user_loader
def load_user(user_id: int) -> Optional[User]:
    """Loads a user from the database."""
    return User.query.get(int(user_id))

@app.route('/')
def index() -> str:
    """Displays the index page."""
    posts = Post.query.all()
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login() -> str:
    """Handles user login."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('You have been logged in.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout() -> str:
    """Logs out the current user."""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register() -> str:
    """Handles user registration."""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('You have been registered.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/post/<int:post_id>')
def post(post_id: int) -> str:
    """Displays a blog post."""
    post = Post.query.get_or_404(post_id)
    comments = Comment.query.filter_by(post_id=post_id).all()
    return render_template('post.html', post=post, comments=comments)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment(post_id: int) -> str:
    """Handles commenting on a blog post."""
    post = Post.query.get_or_404(post_id)
    content = request.form['content']
    comment = Comment(content=content, post_id=post_id, author_id=current_user.id)
    db.session.add(comment)
    db.session.commit()
    flash('Your comment has been posted.', 'success')
    return redirect(url_for('post', post_id=post_id))

@app.route('/post/create', methods=['GET', 'POST'])
@login_required
def create_post() -> str:
    """Handles creating a new blog post."""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        tags = request.form['tags']
        post = Post(title=title, content=content, author_id=current_user.id, category=category, tags=tags)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created.', 'success')
        return redirect(url_for('index'))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id: int) -> str:
    """Handles updating a blog post."""
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        flash('You do not have permission to update this post.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        tags = request.form['tags']
        post.title = title
        post.content = content
        post.category = category
        post.tags = tags
        db.session.commit()
        flash('Your post has been updated.', 'success')
        return redirect(url_for('post', post_id=post_id))
    return render_template('update_post.html', post=post)

@app.route('/post/<int:post_id>/delete')
@login_required
def delete_post(post_id: int) -> str:
    """Handles deleting a blog post."""
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        flash('You do not have permission to delete this post.', 'danger')
        return redirect(url_for('index'))
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)