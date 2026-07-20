"""
Blog Content Management System (CMS) - Complete Flask Implementation
====================================================================

This module implements a full-featured blog CMS with:
- User authentication (register, login, logout)
- CRUD operations for blog posts
- Comment system on posts
- Categories and tags for posts
- CSRF protection, secure password storage, input validation
- Type hints, docstrings, and error handling

Dependencies:
- Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Bcrypt
- (All installable via pip)

Usage:
    Set the FLASK_APP environment variable to this file and run:
        $ flask run
    or directly:
        $ python this_file.py
"""

from typing import Optional, List, Tuple, Any
from datetime import datetime

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from flask_wtf import FlaskForm
from flask_bcrypt import Bcrypt
from wtforms import (
    StringField,
    PasswordField,
    TextAreaField,
    SubmitField,
    SelectMultipleField,
    SelectField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    ValidationError,
    EqualTo,
)

# ----------------------------------------------------------------------
# Application Factory & Configuration
# ----------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-to-a-secure-random-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

# ----------------------------------------------------------------------
# Database Models
# ----------------------------------------------------------------------


class User(UserMixin, db.Model):
    """User model for authentication and author tracking."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False)

    # Relationships
    posts = db.relationship("Post", backref="author", lazy="dynamic", cascade="all, delete-orphan")
    comments = db.relationship("Comment", backref="author", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"User('{self.username}')"


class Category(db.Model):
    """Blog post category."""

    __tablename__ = "categories"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(50), unique=True, nullable=False, index=True)

    posts = db.relationship("Post", backref="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"Category('{self.name}')"


class Tag(db.Model):
    """Blog post tag (many-to-many with posts)."""

    __tablename__ = "tags"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(30), unique=True, nullable=False, index=True)

    # Many-to-many relationship: post_tags table defined later
    posts = db.relationship(
        "Post", secondary="post_tags", back_populates="tags", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"Tag('{self.name}')"


# Association table for Post <-> Tag many-to-many
post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("posts.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class Post(db.Model):
    """Blog post model with title, content, timestamps, and relationships."""

    __tablename__ = "posts"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(100), nullable=False, index=True)
    content: str = db.Column(db.Text, nullable=False)
    date_posted: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    date_updated: Optional[datetime] = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Foreign keys
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id: Optional[int] = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    # Relationships
    comments = db.relationship(
        "Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )
    tags = db.relationship(
        "Tag", secondary=post_tags, back_populates="posts", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"Post('{self.title}', '{self.date_posted}')"


class Comment(db.Model):
    """Comment on a blog post."""

    __tablename__ = "comments"

    id: int = db.Column(db.Integer, primary_key=True)
    content: str = db.Column(db.Text, nullable=False)
    date_posted: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)

    def __repr__(self) -> str:
        return f"Comment('{self.content[:20]}...')"


# ----------------------------------------------------------------------
# Flask-Login User Loader
# ----------------------------------------------------------------------


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user from database by ID."""
    return User.query.get(int(user_id))


# ----------------------------------------------------------------------
# Forms (WTForms with CSRF protection)
# ----------------------------------------------------------------------


class RegistrationForm(FlaskForm):
    """User registration form."""

    username = StringField("Username", validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Sign Up")

    def validate_username(self, username: StringField) -> None:
        """Check if username is already taken."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError("That username is taken. Please choose a different one.")

    def validate_email(self, email: StringField) -> None:
        """Check if email is already registered."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError("That email is already in use.")


class LoginForm(FlaskForm):
    """User login form."""

    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Form for creating/editing blog posts."""

    title = StringField("Title", validators=[DataRequired(), Length(min=1, max=100)])
    content = TextAreaField("Content", validators=[DataRequired()])
    category = SelectField("Category", coerce=int, default=None)
    tags = SelectMultipleField("Tags", coerce=int)
    submit = SubmitField("Post")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Populate select fields with database choices."""
        super().__init__(*args, **kwargs)
        self.category.choices = [
            (c.id, c.name) for c in Category.query.order_by(Category.name).all()
        ]
        # Add a "None" option for optional category
        self.category.choices.insert(0, (0, "No Category"))
        self.tags.choices = [
            (t.id, t.name) for t in Tag.query.order_by(Tag.name).all()
        ]


class CommentForm(FlaskForm):
    """Form for adding a comment."""

    content = TextAreaField("Comment", validators=[DataRequired(), Length(min=1, max=500)])
    submit = SubmitField("Submit Comment")


# ----------------------------------------------------------------------
# Route Handlers
# ----------------------------------------------------------------------


@app.route("/")
@app.route("/home")
def home() -> str:
    """Display all blog posts with pagination."""
    page = request.args.get("page", 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(
        page=page, per_page=5, error_out=False
    )
    return render_template("home.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register() -> str:
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_password,
        )
        db.session.add(user)
        db.session.commit()
        flash("Your account has been created! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=False)
            next_page = request.args.get("next")
            flash("Login successful!", "success")
            return redirect(next_page) if next_page else redirect(url_for("home"))
        else:
            flash("Login unsuccessful. Please check email and password.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
def logout() -> str:
    """Log out the current user."""
    logout_user()
    return redirect(url_for("home"))


@app.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post() -> str:
    """Create a new blog post."""
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data,
            content=form.content.data,
            author=current_user,
            category_id=form.category.data if form.category.data != 0 else None,
        )
        # Add selected tags
        selected_tags = Tag.query.filter(Tag.id.in_(form.tags.data)).all()
        for tag in selected_tags:
            post.tags.append(tag)
        db.session.add(post)
        db.session.commit()
        flash("Your post has been created!", "success")
        return redirect(url_for("post", post_id=post.id))
    return render_template("create_post.html", form=form, legend="New Post")


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def post(post_id: int) -> str:
    """View a single blog post and handle comments."""
    post_obj = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You must be logged in to comment.", "info")
            return redirect(url_for("login"))
        comment = Comment(
            content=form.content.data,
            author=current_user,
            post=post_obj,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comment added!", "success")
        return redirect(url_for("post", post_id=post_obj.id))
    # Paginate comments
    page = request.args.get("page", 1, type=int)
    comments = (
        Comment.query.filter_by(post_id=post_obj.id)
        .order_by(Comment.date_posted.desc())
        .paginate(page=page, per_page=5, error_out=False)
    )
    return render_template(
        "post.html", post=post_obj, comments=comments, form=form
    )


@app.route("/post/<int:post_id>/update", methods=["GET", "POST"])
@login_required
def update_post(post_id: int) -> str:
    """Edit an existing blog post (only author or admin)."""
    post_obj = Post.query.get_or_404(post_id)
    if post_obj.author != current_user and not current_user.is_admin:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post_obj.title = form.title.data
        post_obj.content = form.content.data
        post_obj.category_id = form.category.data if form.category.data != 0 else None
        # Update tags
        post_obj.tags = Tag.query.filter(Tag.id.in_(form.tags.data)).all()
        db.session.commit()
        flash("Post updated!", "success")
        return redirect(url_for("post", post_id=post_obj.id))
    elif request.method == "GET":
        form.title.data = post_obj.title
        form.content.data = post_obj.content
        form.category.data = post_obj.category_id if post_obj.category_id else 0
        form.tags.data = [tag.id for tag in post_obj.tags]
    return render_template("create_post.html", form=form, legend="Update Post")


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id: int) -> str:
    """Delete a blog post (only author or admin)."""
    post_obj = Post.query.get_or_404(post_id)
    if post_obj.author != current_user and not current_user.is_admin:
        abort(403)
    db.session.delete(post_obj)
    db.session.commit()
    flash("Post deleted!", "success")
    return redirect(url_for("home"))


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id: int) -> str:
    """Delete a comment (only comment author, post author, or admin)."""
    comment = Comment.query.get_or_404(comment_id)
    if (
        comment.author != current_user
        and comment.post.author != current_user
        and not current_user.is_admin
    ):
        abort(403)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted!", "success")
    return redirect(url_for("post", post_id=post_id))


@app.route("/category/<string:category_name>")
def category_posts(category_name: str) -> str:
    """List posts filtered by category."""
    category = Category.query.filter_by(name=category_name).first_or_404()
    page = request.args.get("page", 1, type=int)
    posts = (
        Post.query.filter_by(category_id=category.id)
        .order_by(Post.date_posted.desc())
        .paginate(page=page, per_page=5, error_out=False)
    )
    return render_template("home.html", posts=posts, category=category)


@app.route("/tag/<string:tag_name>")
def tag_posts(tag_name: str) -> str:
    """List posts filtered by tag."""
    tag = Tag.query.filter_by(name=tag_name).first_or_404()
    page = request.args.get("page", 1, type=int)
    posts = (
        tag.posts.order_by(Post.date_posted.desc())
        .paginate(page=page, per_page=5, error_out=False)
    )
    return render_template("home.html", posts=posts, tag=tag)


# ----------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------


@app.errorhandler(404)
def not_found(error: Any) -> Tuple[str, int]:
    """Handle 404 errors."""
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(error: Any) -> Tuple[str, int]:
    """Handle 403 errors."""
    return render_template("403.html"), 403


@app.errorhandler(500)
def internal_error(error: Any) -> Tuple[str, int]:
    """Handle 500 errors with database rollback."""
    db.session.rollback()
    return render_template("500.html"), 500


# ----------------------------------------------------------------------
# CLI Commands (for database initialization)
# ----------------------------------------------------------------------


@app.cli.command("init-db")
def init_db() -> None:
    """Initialize the database with tables and some seed data."""
    db.create_all()
    # Add default categories and tags
    cats = ["Technology", "Lifestyle", "Travel", "Food"]
    for cat_name in cats:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))
    tags = ["python", "flask", "tutorial", "news", "review"]
    for tag_name in tags:
        if not Tag.query.filter_by(name=tag_name).first():
            db.session.add(Tag(name=tag_name))
    db.session.commit()
    print("Database initialized with default categories and tags.")


# ----------------------------------------------------------------------
# Application Entry Point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)