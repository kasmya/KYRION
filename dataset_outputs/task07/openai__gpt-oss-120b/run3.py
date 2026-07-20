"""
A minimal blog CMS built with Flask.

Features:
- User registration & authentication (Flask-Login, password hashing)
- CRUD for blog posts
- Categories / tags (many‑to‑many)
- Comment system (approved by author)
- CSRF protection, input validation (Flask-WTF)
- SQLite backend via Flask‑SQLAlchemy
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import (
    BooleanField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
    SelectMultipleField,
)
from wtforms.validators import DataRequired, Email, Length, ValidationError

# --------------------------------------------------------------------------- #
# Application & extensions
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-with-a-strong-random-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
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
    """Application user."""

    __tablename__ = "user"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False, nullable=False)

    posts: List["Post"] = db.relationship("Post", backref="author", lazy="dynamic")
    comments: List["Comment"] = db.relationship(
        "Comment", backref="author", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        """Hash and store a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a password against stored hash."""
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    """Post category (one‑to‑many)."""

    __tablename__ = "category"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(50), unique=True, nullable=False)

    posts: List["Post"] = db.relationship("Post", backref="category", lazy="dynamic")


class Tag(db.Model):
    """Tag used for many‑to‑many relationship with posts."""

    __tablename__ = "tag"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(30), unique=True, nullable=False)


class Post(db.Model):
    """Blog post."""

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
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category_id: Optional[int] = db.Column(
        db.Integer, db.ForeignKey("category.id"), nullable=True
    )

    tags: List[Tag] = db.relationship(
        "Tag", secondary=post_tags, lazy="subquery", backref=db.backref("posts", lazy=True)
    )
    comments: List["Comment"] = db.relationship(
        "Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )


class Comment(db.Model):
    """Comment on a post."""

    __tablename__ = "comment"

    id: int = db.Column(db.Integer, primary_key=True)
    body: str = db.Column(db.Text, nullable=False)
    created_at: dt.datetime = db.Column(
        db.DateTime, default=dt.datetime.utcnow, nullable=False
    )
    approved: bool = db.Column(db.Boolean, default=False, nullable=False)

    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)


# --------------------------------------------------------------------------- #
# Flask‑Login user loader
# --------------------------------------------------------------------------- #
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user from database by primary key."""
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #
class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=25)]
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    submit = SubmitField("Register")

    def validate_username(self, field: StringField) -> None:
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already taken.")

    def validate_email(self, field: StringField) -> None:
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("Email already registered.")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Log In")


class PostForm(FlaskForm):
    title = StringField(
        "Title", validators=[DataRequired(), Length(min=1, max=200)]
    )
    body = TextAreaField("Content", validators=[DataRequired()])
    category = StringField("Category")
    tags = StringField(
        "Tags (comma separated)", description="e.g. python, flask, web"
    )
    submit = SubmitField("Save")


class CommentForm(FlaskForm):
    body = TextAreaField("Comment", validators=[DataRequired(), Length(max=1000)])
    submit = SubmitField("Post Comment")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index() -> str:
    """Show recent posts."""
    posts = (
        Post.query.order_by(Post.created_at.desc())
        .options(db.joinedload(Post.author), db.joinedload(Post.category))
        .limit(10)
        .all()
    )
    return render_template("index.html", posts=posts)


@app.route("/post/<int:post_id>")
def post_detail(post_id: int) -> str:
    """Show a single post with comments and comment form."""
    post = (
        Post.query.filter_by(id=post_id)
        .options(db.joinedload(Post.author), db.joinedload(Post.tags))
        .first_or_404()
    )
    form = CommentForm()
    # Show only approved comments unless author is the owner
    if current_user.is_authenticated and (current_user.id == post.user_id):
        comments = post.comments.order_by(Comment.created_at.asc()).all()
    else:
        comments = (
            post.comments.filter_by(approved=True)
            .order_by(Comment.created_at.asc())
            .all()
        )
    return render_template(
        "post_detail.html", post=post, comments=comments, form=form
    )


@app.route("/post/create", methods=["GET", "POST"])
@login_required
def post_create() -> str:
    """Create a new blog post."""
    form = PostForm()
    if form.validate_on_submit():
        category = None
        if form.category.data:
            category = Category.query.filter_by(name=form.category.data.strip()).first()
            if not category:
                category = Category(name=form.category.data.strip())
                db.session.add(category)
        new_post = Post(
            title=form.title.data.strip(),
            body=form.body.data,
            author=current_user,
            category=category,
        )
        # Process tags
        tag_names = [t.strip() for t in form.tags.data.split(",") if t.strip()]
        for name in tag_names:
            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
                db.session.add(tag)
            new_post.tags.append(tag)

        db.session.add(new_post)
        db.session.commit()
        flash("Post created successfully.", "success")
        return redirect(url_for("post_detail", post_id=new_post.id))

    return render_template("post_form.html", form=form, action="Create")


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id: int) -> str:
    """Edit an existing post (owner only)."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data.strip()
        post.body = form.body.data

        # Category handling
        if form.category.data:
            cat = Category.query.filter_by(name=form.category.data.strip()).first()
            if not cat:
                cat = Category(name=form.category.data.strip())
                db.session.add(cat)
            post.category = cat
        else:
            post.category = None

        # Tags handling
        post.tags.clear()
        tag_names = [t.strip() for t in form.tags.data.split(",") if t.strip()]
        for name in tag_names:
            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
                db.session.add(tag)
            post.tags.append(tag)

        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("post_detail", post_id=post.id))

    # Pre‑populate tags field
    form.tags.data = ", ".join(tag.name for tag in post.tags)
    form.category.data = post.category.name if post.category else ""
    return render_template("post_form.html", form=form, action="Edit")


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def post_delete(post_id: int) -> str:
    """Delete a post (owner or admin)."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and not current_user.is_admin:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("index"))


@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment_create(post_id: int) -> str:
    """Add a comment to a post."""
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            body=form.body.data,
            author=current_user,
            post=post,
            approved=False,  # default: pending moderation
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comment submitted for review.", "info")
    else:
        flash("Failed to submit comment.", "danger")
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/comment/<int:comment_id>/approve", methods=["POST"])
@login_required
def comment_approve(comment_id: int) -> str:
    """Approve a comment (post author only)."""
    comment = Comment.query.get_or_404(comment_id)
    if comment.post.author != current_user:
        abort(403)
    comment.approved = True
    db.session.commit()
    flash("Comment approved.", "success")
    return redirect(url_for("post_detail", post_id=comment.post_id))


@app.route("/register", methods=["GET", "POST"])
def register() -> str:
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout() -> str:
    """Log out the current user."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------- #
# Error handlers
# --------------------------------------------------------------------------- #
@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", error=error), 403


@app.errorhandler(404)
def page_not_found(error):
    return render_template("error.html", error=error), 404


@app.errorhandler(500)
def internal_error(error):
    # In production you'd log the error details.
    return render_template("error.html", error=error), 500


# --------------------------------------------------------------------------- #
# CLI command to initialise the database
# --------------------------------------------------------------------------- #
@app.cli.command("init-db")
def init_db() -> None:
    """Create database tables."""
    db.create_all()
    print("Database initialized.")


# --------------------------------------------------------------------------- #
# Template stubs (for completeness - actual HTML files live in /templates)
# --------------------------------------------------------------------------- #
# The following very small Jinja2 templates are embedded as strings for a
# self‑contained example. In a real project you would place them in the
# `templates/` directory.

from flask import Markup

@app.context_processor
def inject_templates():
    """Inject minimal inline templates for quick testing."""
    templates = {
        "base.html": Markup(
            """
            <!doctype html>
            <html lang="en"><head>
                <meta charset="utf-8"><title>{% block title %}My Blog{% endblock %}</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
            </head><body class="container py-4">
                {% with messages = get_flashed_messages(with_categories=true) %}
                  {% if messages %}
                    {% for category, msg in messages %}
                      <div class="alert alert-{{category}}">{{msg}}</div>
                    {% endfor %}
                  {% endif %}
                {% endwith %}
                <nav class="mb-3">
                    <a class="me-2" href="{{ url_for('index') }}">Home</a>
                    {% if current_user.is_authenticated %}
                        <span class="me-2">Logged in as {{ current_user.username }}</span>
                        <a href="{{ url_for('logout') }}">Logout</a>
                    {% else %}
                        <a href="{{ url_for('login') }}">Login</a>
                        <a href="{{ url_for('register') }}">Register</a>
                    {% endif %}
                </nav>
                {% block content %}{% endblock %}
            </body></html>
            """
        ),
        "index.html": Markup(
            """
            {% extends "base.html" %}
            {% block title %}Recent Posts{% endblock %}
            {% block content %}
            <h1>Recent Posts</h1>
            {% for post in posts %}
              <div class="mb-4">
                <h2><a href="{{ url_for('post_detail', post_id=post.id) }}">{{ post.title }}</a></h2>
                <p class="text-muted">
                    By {{ post.author.username }} on {{ post.created_at.strftime('%Y-%m-%d') }}
                    {% if post.category %} in {{ post.category.name }}{% endif %}
                </p>
                <p>{{ post.body[:200] }}{% if post.body|length > 200 %}…{% endif %}</p>
              </div>
            {% else %}
              <p>No posts yet.</p>
            {% endfor %}
            {% if current_user.is_authenticated %}
                <a class="btn btn-primary" href="{{ url_for('post_create') }}">Create New Post</a>
            {% endif %}
            {% endblock %}
            """
        ),
        "post_detail.html": Markup(
            """
            {% extends "base.html" %}
            {% block title %}{{ post.title }}{% endblock %}
            {% block content %}
            <h1>{{ post.title }}</h1>
            <p class="text-muted">
                By {{ post.author.username }} on {{ post.created_at.strftime('%Y-%m-%d') }}
                {% if post.category %} in {{ post.category.name }}{% endif %}
            </p>
            <div class="mb-4">{{ post.body|nl2br }}</div>

            {% if current_user.is_authenticated and current_user.id == post.author.id %}
                <a class="btn btn-secondary me-2" href="{{ url_for('post_edit', post_id=post.id) }}">Edit</a>
                <form method="post" action="{{ url_for('post_delete', post_id=post.id) }}" style="display:inline;">
                    {{ csrf_token() }}
                    <button class="btn btn-danger" onclick="return confirm('Delete this post?');">Delete</