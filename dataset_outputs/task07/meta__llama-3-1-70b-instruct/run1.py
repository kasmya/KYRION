from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    """User model."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        """Set password."""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Check password."""
        return check_password_hash(self.password, password)

class Post(db.Model):
    """Post model."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy=True)
    categories = db.relationship('Category', backref='post', lazy=True)

class Comment(db.Model):
    """Comment model."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Category(db.Model):
    """Category model."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    """Load user."""
    return User.query.get(int(user_id))

@app.route('/')
def home():
    """Home page."""
    posts = Post.query.all()
    return render_template('home.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register page."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.', 'danger')
        else:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout page."""
    logout_user()
    flash('Logout successful.', 'success')
    return redirect(url_for('home'))

@app.route('/create-post', methods=['GET', 'POST'])
@login_required
def create_post():
    """Create post page."""
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        new_post = Post(title=title, content=content, author=current_user)
        db.session.add(new_post)
        db.session.commit()
        flash('Post created successfully.', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
def post(post_id):
    """Post page."""
    post = Post.query.get_or_404(post_id)
    comments = post.comments
    return render_template('post.html', post=post, comments=comments)

@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    """Update post page."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    if request.method == 'POST':
        post.title = request.form.get('title')
        post.content = request.form.get('content')
        db.session.commit()
        flash('Post updated successfully.', 'success')
        return redirect(url_for('post', post_id=post.id))
    return render_template('update_post.html', post=post)

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    """Delete post page."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment(post_id):
    """Comment page."""
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    new_comment = Comment(content=content, user_id=current_user.id, post_id=post.id)
    db.session.add(new_comment)
    db.session.commit()
    flash('Comment added successfully.', 'success')
    return redirect(url_for('post', post_id=post.id))

@app.route('/post/<int:post_id>/category', methods=['POST'])
@login_required
def category(post_id):
    """Category page."""
    post = Post.query.get_or_404(post_id)
    name = request.form.get('name')
    new_category = Category(name=name, post_id=post.id)
    db.session.add(new_category)
    db.session.commit()
    flash('Category added successfully.', 'success')
    return redirect(url_for('post', post_id=post.id))

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)