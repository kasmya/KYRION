"""
A minimal blog Content Management System (CMS) built with Flask.

Features:
- User registration and authentication (Flask-Login)
- CRUD for blog posts
- Comment system
- Categories and tags (many‑to‑many)
- Input validation (WTForms) and CSRF protection
- SQLite storage via SQLAlchemy
"""

from __future__ import annotations

import os
import datetime as dt
from typing import List, Optional

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    current_user,
    login_required,
)
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Length, Email, ValidationError, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------------------------------- #
# Flask app and extensions initialization
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///blog.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """User model for authentication."""

    __tablename__ = "user"
    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False)

    posts: List["Post"] = db.relationship("Post", backref="author", lazy="dynamic")
    comments: List["Comment"] = db.relationship(
        "Comment", backref="author", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Validate password against stored hash."""
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    """Post category (one‑to‑many)."""

    __tablename__ = "category"
    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(50), unique=True, nullable=False)

    posts: List["Post"] = db.relationship("Post", backref="category", lazy="dynamic")


class Tag(db.Model):
    """Tag model for many‑to‑many relationship with posts."""

    __tablename__ = "tag"
    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(30), unique=True, nullable=False)


class Post(db.Model):
    """Blog post model."""

    __tablename__ = "post"
    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    body: str = db.Column(db.Text, nullable=False)
    created_at: dt.datetime = db.Column(
        db.DateTime, default=dt.datetime.utcnow, nullable=False
    )
    updated_at: dt.datetime = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    author_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category_id: Optional[int] = db.Column(
        db.Integer, db.ForeignKey("category.id")
    )

    tags: List[Tag] = db.relationship(
        "Tag", secondary=post_tags, lazy="subquery", backref=db.backref("posts", lazy=True)
    )
    comments: List["Comment"] = db.relationship(
        "Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )


class Comment(db.Model):
    """Comment model attached to a post."""

    __tablename__ = "comment"
    id: int = db.Column(db.Integer, primary_key=True)
    body: str = db.Column(db.Text, nullable=False)
    created_at: dt.datetime = db.Column(
        db.DateTime, default=dt.datetime.utcnow, nullable=False
    )
    author_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)


# --------------------------------------------------------------------------- #
# Flask‑Login loader
# --------------------------------------------------------------------------- #
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #
class RegistrationForm(FlaskForm):
    """User registration form."""

    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=25)],
        render_kw={"autocomplete": "username"},
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=6)],
        render_kw={"autocomplete": "new-password"},
    )
    confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Register")

    def validate_username(self, field: StringField) -> None:
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already taken.")

    def validate_email(self, field: StringField) -> None:
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("Email already registered.")


class LoginForm(FlaskForm):
    """User login form."""

    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "current-password"},
    )
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Create / edit post."""

    title = StringField(
        "Title", validators=[DataRequired(), Length(min=5, max=200)]
    )
    body = TextAreaField("Content", validators=[DataRequired(), Length(min=10)])
    category = StringField("Category", validators=[Length(max=50)])
    tags = StringField(
        "Tags (comma separated)", description="Enter tags separated by commas."
    )
    submit = SubmitField("Save")


class CommentForm(FlaskForm):
    """Add a comment."""

    body = TextAreaField(
        "Comment", validators=[DataRequired(), Length(min=1, max=1000)]
    )
    submit = SubmitField("Post Comment")


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #
def _get_or_create_tag(name: str) -> Tag:
    tag = Tag.query.filter_by(name=name).first()
    if not tag:
        tag = Tag(name=name)
        db.session.add(tag)
        db.session.flush()
    return tag


def _parse_tags(tag_string: str) -> List[Tag]:
    """Parse comma‑separated tags."""
    tags = []
    for raw in tag_string.split(","):
        name = raw.strip().lower()
        if name:
            tags.append(_get_or_create_tag(name))
    return tags


def _get_or_create_category(name: str) -> Optional[Category]:
    if not name:
        return None
    name = name.strip()
    category = Category.query.filter_by(name=name).first()
    if not category:
        category = Category(name=name)
        db.session.add(category)
        db.session.flush()
    return category


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index() -> str:
    """Home page – list posts."""
    posts = (
        Post.query.order_by(Post.created_at.desc())
        .options(db.selectinload(Post.author), db.selectinload(Post.tags))
        .all()
    )
    return render_template("index.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register() -> str:
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful, you can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout() -> str:
    """Log the user out."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>")
def post_detail(post_id: int) -> str:
    """Show a single post and its comments."""
    post = (
        Post.query.filter_by(id=post_id)
        .options(
            db.selectinload(Post.author),
            db.selectinload(Post.tags),
            db.selectinload(Post.comments).selectinload(Comment.author),
        )
        .first_or_404()
    )
    comment_form = CommentForm()
    return render_template(
        "post_detail.html", post=post, comment_form=comment_form
    )


@app.route("/post/create", methods=["GET", "POST"])
@login_required
def post_create() -> str:
    """Create a new blog post."""
    form = PostForm()
    if form.validate_on_submit():
        category = _get_or_create_category(form.category.data)
        tags = _parse_tags(form.tags.data)
        new_post = Post(
            title=form.title.data,
            body=form.body.data,
            author=current_user,
            category=category,
        )
        new_post.tags = tags
        db.session.add(new_post)
        db.session.commit()
        flash("Post created.", "success")
        return redirect(url_for("post_detail", post_id=new_post.id))
    return render_template("post_form.html", form=form, action="Create")


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id: int) -> str:
    """Edit an existing post – only author or admin."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and not current_user.is_admin:
        abort(403)

    form = PostForm(
        title=post.title,
        body=post.body,
        category=post.category.name if post.category else "",
        tags=", ".join(tag.name for tag in post.tags),
    )
    if form.validate_on_submit():
        post.title = form.title.data
        post.body = form.body.data
        post.category = _get_or_create_category(form.category.data)
        post.tags = _parse_tags(form.tags.data)
        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("post_detail", post_id=post.id))
    return render_template("post_form.html", form=form, action="Edit")


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def post_delete(post_id: int) -> str:
    """Delete post – CSRF‑protected."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and not current_user.is_admin:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id: int) -> str:
    """Add a comment to a post."""
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            body=form.body.data,
            author=current_user,
            post=post,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comment added.", "success")
    else:
        flash("Failed to add comment.", "danger")
    return redirect(url_for("post_detail", post_id=post.id))


# --------------------------------------------------------------------------- #
# Error handlers
# --------------------------------------------------------------------------- #
@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="Forbidden"), 403


@app.errorhandler(404)
def page_not_found(error):
    return render_template("error.html", code=404, message="Page not found"), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return (
        render_template("error.html", code=500, message="Internal server error"),
        500,
    )


# --------------------------------------------------------------------------- #
# CLI command to initialise the database
# --------------------------------------------------------------------------- #
@app.cli.command("init-db")
def init_db() -> None:
    """Create database tables."""
    db.create_all()
    print("Database initialized.")


# --------------------------------------------------------------------------- #
# Template stubs (normally separate HTML files, kept minimal for demo)
# --------------------------------------------------------------------------- #
@app.context_processor
def inject_now():
    return {"now": dt.datetime.utcnow()}


def _render_template_stub(name: str, **context):
    """Fallback simple renderer if templates are missing."""
    return f"<h1>{name}</h1><pre>{context}</pre>"


# Monkey‑patch render_template for this single‑file demo.
# In a real project, proper Jinja2 templates live in a /templates directory.
render_template = _render_template_stub  # type: ignore


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Ensure the DB file exists before first request.
    if not os.path.exists("blog.db"):
        with app.app_context():
            db.create_all()
    app.run(debug=True)