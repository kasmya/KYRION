from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, or_
from typing import Optional, List
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# ------------------ Models ------------------
class User(UserMixin, db.Model):
    """User model for authentication and ownership."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    votes = db.relationship('Vote', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify the password against the hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.username}>'

class Post(db.Model):
    """Post model for forum threads."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    votes = db.relationship('Vote', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def upvotes(self) -> int:
        """Return count of upvotes (vote_value=1)."""
        return Vote.query.filter_by(post_id=self.id, vote_value=1).count()

    @property
    def downvotes(self) -> int:
        """Return count of downvotes (vote_value=-1)."""
        return Vote.query.filter_by(post_id=self.id, vote_value=-1).count()

    @property
    def score(self) -> int:
        """Net score (upvotes - downvotes)."""
        return self.upvotes - self.downvotes

    def user_vote(self, user: User) -> Optional[int]:
        """Return the vote value of a user for this post, or None if not voted."""
        vote = Vote.query.filter_by(user_id=user.id, post_id=self.id).first()
        return vote.vote_value if vote else None

    def __repr__(self) -> str:
        return f'<Post {self.title[:50]}>'

class Comment(db.Model):
    """Comment model for replies to posts."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    def __repr__(self) -> str:
        return f'<Comment by {self.author.username}>'

class Vote(db.Model):
    """Vote model for upvote/downvote on posts."""
    id = db.Column(db.Integer, primary_key=True)
    vote_value = db.Column(db.Integer, nullable=False)  # 1 for upvote, -1 for downvote
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_user_post_vote'),)

    def __repr__(self) -> str:
        return f'<Vote {self.vote_value} by {self.user.username}>'

# ------------------ Forms ------------------
class RegistrationForm(FlaskForm):
    """Form for user registration."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username: StringField) -> None:
        """Check if username already exists."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken.')

    def validate_email(self, email: StringField) -> None:
        """Check if email already registered."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered.')

class LoginForm(FlaskForm):
    """Form for user login."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PostForm(FlaskForm):
    """Form for creating/editing a post."""
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Submit')

class CommentForm(FlaskForm):
    """Form for adding a comment."""
    content = TextAreaField('Comment', validators=[DataRequired()])
    submit = SubmitField('Post Comment')

class SearchForm(FlaskForm):
    """Form for searching posts."""
    query = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Search')

# ------------------ User Loader ------------------
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))

# ------------------ Routes ------------------
@app.route('/')
def index() -> str:
    """Homepage: show paginated posts ordered by newest first."""
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register() -> str:
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        try:
            db.session.add(user)
            db.session.commit()
            flash('Account created! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            app.logger.error(f'Registration error: {e}')
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login() -> str:
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout() -> str:
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post() -> str:
    """Create a new post."""
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user)
        try:
            db.session.add(post)
            db.session.commit()
            flash('Your post has been created!', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            app.logger.error(f'Create post error: {e}')
    return render_template('create_post.html', form=form, title='New Post')

@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id: int) -> str:
    """View a single post and its comments."""
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('Please log in to comment.', 'warning')
            return redirect(url_for('login'))
        comment = Comment(content=form.content.data, author=current_user, post=post)
        try:
            db.session.add(comment)
            db.session.commit()
            flash('Your comment has been posted.', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            app.logger.error(f'Add comment error: {e}')
    return render_template('view_post.html', post=post, form=form)

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id: int) -> str:
    """Edit a post owned by the current user."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        try:
            db.session.commit()
            flash('Post updated!', 'success')
            return redirect(url_for('view_post', post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred.', 'danger')
            app.logger.error(f'Edit post error: {e}')
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('create_post.html', form=form, title='Edit Post')

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id: int) -> str:
    """Delete a post owned by the current user."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    try:
        db.session.delete(post)
        db.session.commit()
        flash('Post deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'danger')
        app.logger.error(f'Delete post error: {e}')
    return redirect(url_for('index'))

@app.route('/post/<int:post_id>/vote/<int:value>', methods=['POST'])
@login_required
def vote_post(post_id: int, value: int) -> str:
    """
    Vote on a post. value should be 1 (upvote) or -1 (downvote).
    If user already voted with same value, remove the vote (toggle off).
    If different value, update the vote.
    """
    if value not in (1, -1):
        abort(400)
    post = Post.query.get_or_404(post_id)
    if post.author == current_user:
        flash('You cannot vote on your own post.', 'warning')
        return redirect(url_for('view_post', post_id=post.id))
    existing_vote = Vote.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    try:
        if existing_vote:
            if existing_vote.vote_value == value:
                # Remove vote
                db.session.delete(existing_vote)
                flash('Vote removed.', 'info')
            else:
                existing_vote.vote_value = value
                flash('Vote updated.', 'info')
        else:
            vote = Vote(vote_value=value, user_id=current_user.id, post_id=post.id)
            db.session.add(vote)
            flash('Vote recorded.', 'success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('An error occurred.', 'danger')
        app.logger.error(f'Vote error: {e}')
    return redirect(url_for('view_post', post_id=post.id))

@app.route('/search', methods=['GET', 'POST'])
def search() -> str:
    """Search posts by title or content using LIKE."""
    form = SearchForm()
    query = request.args.get('query', '')
    page = request.args.get('page', 1, type=int)
    results: List[Post] = []
    if query:
        search_term = f'%{query}%'
        results = Post.query.filter(
            or_(Post.title.like(search_term), Post.content.like(search_term))
        ).order_by(Post.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    else:
        results = Post.query.order_by(Post.created_at.desc()).paginate(page=1, per_page=10, error_out=False)
    return render_template('search.html', form=form, results=results, query=query)

# ------------------ Error Handlers ------------------
@app.errorhandler(404)
def not_found(error) -> str:
    """Return 404 page."""
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(error) -> str:
    """Return 403 page."""
    return render_template('403.html'), 403

@app.errorhandler(500)
def internal_error(error) -> str:
    """Return 500 page."""
    db.session.rollback()
    return render_template('500.html'), 500

# ------------------ Database Initialization ------------------
def create_tables() -> None:
    """Create database tables if they don't exist."""
    db.create_all()

# ------------------ Run ------------------
if __name__ == '__main__':
    create_tables()
    app.run(debug=True)