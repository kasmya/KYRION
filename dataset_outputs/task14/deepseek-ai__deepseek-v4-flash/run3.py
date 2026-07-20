"""
Flask-based forum/discussion board application with user authentication,
post CRUD, comments, voting, and search.
"""

# Standard library and Flask extensions
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

# ----------------------------------------------------------------------
# App & Database Configuration
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()  # In production, use a fixed secret
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# ----------------------------------------------------------------------
# Database Models
# ----------------------------------------------------------------------
class User(UserMixin, db.Model):
    """Represents a registered user."""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')
    votes = db.relationship('Vote', backref='user', lazy='dynamic')

    def set_password(self, password: str) -> None:
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.username}>'


class Post(db.Model):
    """Represents a forum post."""
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    votes = db.relationship('Vote', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def upvotes(self) -> int:
        """Count of upvotes on this post."""
        return self.votes.filter_by(value=1).count()

    @property
    def downvotes(self) -> int:
        """Count of downvotes on this post."""
        return self.votes.filter_by(value=-1).count()

    @property
    def score(self) -> int:
        """Net upvote/downvote score."""
        return self.upvotes - self.downvotes

    def __repr__(self) -> str:
        return f'<Post {self.title}>'


class Comment(db.Model):
    """Represents a comment on a post."""
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)

    def __repr__(self) -> str:
        return f'<Comment {self.id} on Post {self.post_id}>'


class Vote(db.Model):
    """Represents an upvote (value=1) or downvote (value=-1) on a post."""
    __tablename__ = 'votes'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)  # 1 or -1
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='unique_user_post_vote'),
    )

    def __repr__(self) -> str:
        return f'<Vote by User {self.user_id} on Post {self.post_id}>'


# ----------------------------------------------------------------------
# User Loader
# ----------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Flask-Login user loader callback."""
    return User.query.get(int(user_id))


# ----------------------------------------------------------------------
# Forms (using Flask-WTF)
# ----------------------------------------------------------------------
class RegistrationForm(FlaskForm):
    """User registration form."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username: StringField) -> None:
        """Check for duplicate username."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken. Choose a different one.')

    def validate_email(self, email: StringField) -> None:
        """Check for duplicate email."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Use a different one.')


class LoginForm(FlaskForm):
    """User login form."""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class PostForm(FlaskForm):
    """Create or edit a post."""
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Submit')


class CommentForm(FlaskForm):
    """Add a comment."""
    content = TextAreaField('Comment', validators=[DataRequired()])
    submit = SubmitField('Post Comment')


class SearchForm(FlaskForm):
    """Search posts by keyword."""
    query = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Search')


# ----------------------------------------------------------------------
# Routes - Authentication
# ----------------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Account created! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')
            app.logger.error(f'Registration error: {e}')
    return render_template('register.html', title='Register', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


# ----------------------------------------------------------------------
# Routes - Posts
# ----------------------------------------------------------------------
@app.route('/')
@app.route('/home')
def home():
    """Display all posts with pagination."""
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    return render_template('home.html', posts=posts)


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    """Create a new post."""
    form = PostForm()
    if form.validate_on_submit():
        try:
            post = Post(title=form.title.data, content=form.content.data, author=current_user)
            db.session.add(post)
            db.session.commit()
            flash('Your post has been created!', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('Failed to create post.', 'danger')
            app.logger.error(f'Post creation error: {e}')
    return render_template('create_post.html', title='New Post', form=form)


@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id: int):
    """View a single post and its comments. Allow comment submission."""
    post = Post.query.get_or_404(post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('You need to login to comment.', 'warning')
            return redirect(url_for('login'))
        try:
            comment = Comment(content=comment_form.content.data, author=current_user, post=post)
            db.session.add(comment)
            db.session.commit()
            flash('Comment added!', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('Failed to add comment.', 'danger')
            app.logger.error(f'Comment error: {e}')
    comments = Comment.query.filter_by(post_id=post.id).order_by(Comment.created_at.asc()).all()
    return render_template('view_post.html', title=post.title, post=post, comments=comments, comment_form=comment_form)


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id: int):
    """Edit an existing post. Only author can edit."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        try:
            post.title = form.title.data
            post.content = form.content.data
            post.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Post updated!', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update post.', 'danger')
            app.logger.error(f'Post edit error: {e}')
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('create_post.html', title='Edit Post', form=form, legend='Edit Post')


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id: int):
    """Delete a post. Only author or admin can delete."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    try:
        db.session.delete(post)
        db.session.commit()
        flash('Post deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete post.', 'danger')
        app.logger.error(f'Post delete error: {e}')
    return redirect(url_for('home'))


# ----------------------------------------------------------------------
# Routes - Voting
# ----------------------------------------------------------------------
@app.route('/post/<int:post_id>/vote/<int:value>', methods=['POST'])
@login_required
def vote_post(post_id: int, value: int):
    """
    Upvote (value=1) or downvote (value=-1) a post.
    Toggles: if same vote exists, remove it; if opposite, change; otherwise add.
    """
    if value not in (1, -1):
        abort(400, 'Invalid vote value.')
    post = Post.query.get_or_404(post_id)
    if post.author == current_user:
        flash('You cannot vote on your own post.', 'warning')
        return redirect(url_for('view_post', post_id=post_id))

    vote = Vote.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    try:
        if vote:
            if vote.value == value:
                # Remove vote (toggle off)
                db.session.delete(vote)
                flash('Vote removed.', 'info')
            else:
                # Change vote
                vote.value = value
                flash('Vote updated.', 'info')
        else:
            vote = Vote(value=value, user=current_user, post=post)
            db.session.add(vote)
            flash('Vote recorded.', 'success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Failed to process vote.', 'danger')
        app.logger.error(f'Vote error: {e}')
    return redirect(url_for('view_post', post_id=post_id))


# ----------------------------------------------------------------------
# Routes - Search
# ----------------------------------------------------------------------
@app.route('/search', methods=['GET', 'POST'])
def search():
    """Search posts by title or content keywords."""
    form = SearchForm()
    results = []
    if form.validate_on_submit():
        query = form.query.data
        if query:
            # Use ILIKE for PostgreSQL; for SQLite use LIKE (case-insensitive with collate NOCASE)
            # Searching both title and content
            results = Post.query.filter(
                db.or_(
                    Post.title.ilike(f'%{query}%'),
                    Post.content.ilike(f'%{query}%')
                )
            ).order_by(Post.created_at.desc()).all()
    elif request.args.get('q'):
        # Allow GET requests with 'q' parameter
        query = request.args.get('q', '')
        form.query.data = query
        results = Post.query.filter(
            db.or_(
                Post.title.ilike(f'%{query}%'),
                Post.content.ilike(f'%{query}%')
            )
        ).order_by(Post.created_at.desc()).all()
    return render_template('search.html', title='Search', form=form, results=results)


# ----------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('404.html', title='Not Found'), 404


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors."""
    return render_template('403.html', title='Forbidden'), 403


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return render_template('500.html', title='Server Error'), 500


# ----------------------------------------------------------------------
# Entry Point & Database Initialization
# ----------------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)