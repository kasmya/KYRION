from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    """Represents a user in the database."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password: str) -> None:
        """Sets the password for the user."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Checks if the provided password is correct."""
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    """Represents a post in the database."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))

class Comment(db.Model):
    """Represents a comment in the database."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    post = db.relationship('Post', backref=db.backref('comments', lazy=True))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref=db.backref('comments', lazy=True))

class Vote(db.Model):
    """Represents a vote in the database."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    post = db.relationship('Post', backref=db.backref('votes', lazy=True))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('votes', lazy=True))
    value = db.Column(db.Integer, nullable=False)  # 1 for upvote, -1 for downvote

login_manager = LoginManager(app)

@login_manager.user_loader
def load_user(user_id: int) -> Optional[User]:
    """Loads a user from the database."""
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register() -> str:
    """Registers a new user."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already taken')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login() -> str:
    """Logs in a user."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout() -> str:
    """Logs out a user."""
    logout_user()
    return redirect(url_for('index'))

@app.route('/post', methods=['GET', 'POST'])
@login_required
def create_post() -> str:
    """Creates a new post."""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        post = Post(title=title, content=content, author=current_user)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
def view_post(post_id: int) -> str:
    """Displays a post."""
    post = Post.query.get(post_id)
    if post:
        return render_template('view_post.html', post=post)
    else:
        flash('Post not found')
        return redirect(url_for('index'))

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id: int) -> str:
    """Edits a post."""
    post = Post.query.get(post_id)
    if post and post.author == current_user:
        if request.method == 'POST':
            post.title = request.form['title']
            post.content = request.form['content']
            db.session.commit()
            return redirect(url_for('view_post', post_id=post_id))
        return render_template('edit_post.html', post=post)
    else:
        flash('You do not have permission to edit this post')
        return redirect(url_for('index'))

@app.route('/post/<int:post_id>/delete')
@login_required
def delete_post(post_id: int) -> str:
    """Deletes a post."""
    post = Post.query.get(post_id)
    if post and post.author == current_user:
        db.session.delete(post)
        db.session.commit()
        return redirect(url_for('index'))
    else:
        flash('You do not have permission to delete this post')
        return redirect(url_for('index'))

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_post(post_id: int) -> str:
    """Comments on a post."""
    post = Post.query.get(post_id)
    if post:
        content = request.form['content']
        comment = Comment(content=content, post=post, author=current_user)
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for('view_post', post_id=post_id))
    else:
        flash('Post not found')
        return redirect(url_for('index'))

@app.route('/post/<int:post_id>/vote', methods=['POST'])
@login_required
def vote_post(post_id: int) -> str:
    """Votes on a post."""
    post = Post.query.get(post_id)
    if post:
        value = int(request.form['value'])
        vote = Vote.query.filter_by(post=post, user=current_user).first()
        if vote:
            if vote.value == value:
                db.session.delete(vote)
            else:
                vote.value = value
            db.session.commit()
        else:
            vote = Vote(post=post, user=current_user, value=value)
            db.session.add(vote)
            db.session.commit()
        return redirect(url_for('view_post', post_id=post_id))
    else:
        flash('Post not found')
        return redirect(url_for('index'))

@app.route('/search', methods=['GET', 'POST'])
def search() -> str:
    """Searches for posts."""
    if request.method == 'POST':
        query = request.form['query']
        posts = Post.query.filter(Post.title.like(f'%{query}%') | Post.content.like(f'%{query}%')).all()
        return render_template('search_results.html', posts=posts)
    return render_template('search.html')

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)