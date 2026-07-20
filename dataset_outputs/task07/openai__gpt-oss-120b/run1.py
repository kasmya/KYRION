"""
A minimal yet complete Flask‑based Blog Content Management System (CMS).

Features
--------
* User registration, login and logout (Flask‑Login)
* CRUD operations for blog posts
* Post categories and tags (many‑to‑many relationships)
* Comment system (create, read, delete)
* Input validation (Flask‑WTF / WTForms)
* Secure password handling (Werkzeug)
* CSRF protection, JSON API responses, and basic error handling

Run
---
>>> export FLASK_APP=blog_cms.py
>>> flask run
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
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
    validators,
)

# ----------------------------------------------------------------------
# App & Extensions Initialization
# ----------------------------------------------------------------------
app: Flask = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-to-a-strong-random-value")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///blog_cms.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db: SQLAlchemy = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)


# ----------------------------------------------------------------------
# Database Models
# ----------------------------------------------------------------------
post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """User account."""

    __tablename__ = "user"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False, nullable=False)

    posts: List[Post] = db.relationship("Post", backref="author", lazy="dynamic")
    comments: List[Comment] = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Category(db.Model):
    """Category for grouping posts."""

    __tablename__ = "category"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(50), unique=True, nullable=False)

    posts: List[Post] = db.relationship("Post", backref="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Tag(db.Model):
    """Tag for labeling posts."""

    __tablename__ = "tag"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(30), unique=True, nullable=False)

    posts: List[Post] = db.relationship(
        "Post", secondary=post_tags, back_populates="tags", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


class Post(db.Model):
    """Blog post."""

    __tablename__ = "post"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    body: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category_id: Optional[int] = db.Column(
        db.Integer, db.ForeignKey("category.id"), nullable=True
    )

    tags: List[Tag] = db.relationship(
        "Tag", secondary=post_tags, back_populates="posts", lazy="dynamic"
    )
    comments: List[Comment] = db.relationship(
        "Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )

    def as_dict(self) -> Dict[str, Any]:
        """Serialize the post to a dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "author": self.author.username,
            "category": self.category.name if self.category else None,
            "tags": [tag.name for tag in self.tags],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Post {self.title}>"


class Comment(db.Model):
    """Comment on a post."""

    __tablename__ = "comment"

    id: int = db.Column(db.Integer, primary_key=True)
    body: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    def as_dict(self) -> Dict[str, Any]:
        """Serialize the comment to a dictionary."""
        return {
            "id": self.id,
            "body": self.body,
            "author": self.author.username,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Comment {self.id} on Post {self.post_id}>"


# ----------------------------------------------------------------------
# Flask‑Login User Loader
# ----------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return User.query.get(int(user_id))


# ----------------------------------------------------------------------
# Forms
# ----------------------------------------------------------------------
class RegistrationForm(FlaskForm):
    """User registration form."""

    username = StringField(
        "Username",
        validators=[
            validators.DataRequired(),
            validators.Length(min=3, max=25),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            validators.DataRequired(),
            validators.Email(),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            validators.DataRequired(),
            validators.Length(min=8),
        ],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            validators.DataRequired(),
            validators.EqualTo("password", message="Passwords must match"),
        ],
    )
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    """User login form."""

    email = StringField(
        "Email", validators=[validators.DataRequired(), validators.Email()]
    )
    password = PasswordField("Password", validators=[validators.DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Create / edit post."""

    title = StringField(
        "Title", validators=[validators.DataRequired(), validators.Length(max=200)]
    )
    body = TextAreaField("Body", validators=[validators.DataRequired()])
    category = StringField("Category (optional)")
    tags = StringField(
        "Tags (comma‑separated, optional)",
        description="Separate multiple tags with commas",
    )
    submit = SubmitField("Save")


class CommentForm(FlaskForm):
    """Add a comment."""

    body = TextAreaField("Comment", validators=[validators.DataRequired()])
    submit = SubmitField("Post Comment")


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def get_or_create_category(name: str) -> Optional[Category]:
    """Return a Category object, creating it if necessary."""
    name = name.strip()
    if not name:
        return None
    category = Category.query.filter_by(name=name).first()
    if not category:
        category = Category(name=name)
        db.session.add(category)
        db.session.commit()
    return category


def get_or_create_tags(tag_string: str) -> List[Tag]:
    """Parse a comma‑separated tag string and return a list of Tag objects."""
    tags: List[Tag] = []
    for raw_name in tag_string.split(","):
        name = raw_name.strip().lower()
        if not name:
            continue
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name)
            db.session.add(tag)
            db.session.flush()  # obtain ID without committing yet
        tags.append(tag)
    db.session.commit()
    return tags


def json_error(message: str, status_code: int = 400) -> Any:
    """Return a JSON error response."""
    response = jsonify({"error": message})
    response.status_code = status_code
    return response


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index() -> Any:
    """Show the most recent posts."""
    posts = Post.query.order_by(Post.created_at.desc()).limit(10).all()
    # For simplicity we return JSON; replace with render_template for HTML UI.
    return jsonify([post.as_dict() for post in posts])


@app.route("/register", methods=["GET", "POST"])
def register() -> Any:
    """User registration endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email already registered", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already taken", "danger")
            return redirect(url_for("register"))
        user = User(
            username=form.username.data,
            email=form.email.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    # Simple JSON error handling for API usage
    if request.method == "POST":
        return json_error("Invalid registration data")
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login() -> Any:
    """User login endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash("Logged in successfully.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        return json_error("Invalid login data")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout() -> Any:
    """Log out the current user."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/post/new", methods=["GET", "POST"])
@login_required
def create_post() -> Any:
    """Create a new blog post."""
    form = PostForm()
    if form.validate_on_submit():
        category = get_or_create_category(form.category.data or "")
        tags = get_or_create_tags(form.tags.data or "")
        post = Post(
            title=form.title.data,
            body=form.body.data,
            author=current_user,
            category=category,
        )
        post.tags.extend(tags)
        db.session.add(post)
        db.session.commit()
        flash("Post created.", "success")
        return redirect(url_for("view_post", post_id=post.id))
    if request.method == "POST":
        return json_error("Invalid post data")
    return render_template("post_form.html", form=form, action="Create")


@app.route("/post/<int:post_id>")
def view_post(post_id: int) -> Any:
    """Retrieve a single post with its comments."""
    post = Post.query.get_or_404(post_id)
    comments = [c.as_dict() for c in post.comments.order_by(Comment.created_at.asc())]
    data = post.as_dict()
    data["comments"] = comments
    return jsonify(data)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int) -> Any:
    """Edit an existing post; only the author or an admin may edit."""
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
        post.category = get_or_create_category(form.category.data or "")
        post.tags = []  # clear existing tags
        post.tags.extend(get_or_create_tags(form.tags.data or ""))
        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("view_post", post_id=post.id))
    if request.method == "POST":
        return json_error("Invalid edit data")
    return render_template("post_form.html", form=form, action="Edit")


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
@csrf.exempt  # CSRF token is required for form submissions; for API calls you may need token handling.
def delete_post(post_id: int) -> Any:
    """Delete a post; only author or admin."""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and not current_user.is_admin:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id: int) -> Any:
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
        return redirect(url_for("view_post", post_id=post.id))
    return json_error("Invalid comment data")


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id: int) -> Any:
    """Delete a comment; only the comment author or an admin."""
    comment = Comment.query.get_or_404(comment_id)
    if comment.author != current_user and not current_user.is_admin:
        abort(403)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "info")
    return redirect(url_for("view_post", post_id=post_id))


# ----------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(error: Exception) -> Any:
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(403)
def forbidden(error: Exception) -> Any:
    return jsonify({"error": "Forbidden"}), 403


@app.errorhandler(500)
def internal_error(error: Exception) -> Any:
    # In production you would log the error details.
    return jsonify({"error": "Internal server error"}), 500


# ----------------------------------------------------------------------
# CLI Commands
# ----------------------------------------------------------------------
@app.cli.command("init-db")
def init_db() -> None:
    """Initialize the database."""
    db.drop_all()
    db.create_all()
    # Optionally create a default admin user.
    admin = User(username="admin", email="admin@example.com", is_admin=True)
    admin.set_password("ChangeMe123!")
    db.session.add(admin)
    db.session.commit()
    print("Database initialized with admin user (admin@example.com / ChangeMe123!)")


# ----------------------------------------------------------------------
# Run the Application
# ----------------------------------------------------------------------
if __name__ == "__