"""
Blog Content Management System (CMS)
A Flask-based application with user authentication, post CRUD, comments, categories, and tags.
"""

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    TextAreaField,
    SelectMultipleField,
    SubmitField,
    BooleanField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    EqualTo,
    ValidationError,
    Email,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from typing import Optional, List, Tuple

# -----------------------------------------------------------------------------
# Application Setup
# -----------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------

# Association table for many-to-many relationship between Post and Tag
post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("posts.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """User model for authentication."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_admin: bool = db.Column(db.Boolean, default=False)

    posts = db.relationship("Post", backref="author", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify the password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Category(db.Model):
    """Post categories."""

    __tablename__ = "categories"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description: Optional[str] = db.Column(db.String(200))

    posts = db.relationship("Post", backref="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Tag(db.Model):
    """Post tags."""

    __tablename__ = "tags"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(40), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


class Post(db.Model):
    """Blog post."""

    __tablename__ = "posts"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    content: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at: datetime = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id: Optional[int] = db.Column(db.Integer, db.ForeignKey("categories.id"))

    tags = db.relationship("Tag", secondary=post_tags, backref=db.backref("posts", lazy="dynamic"))
    comments = db.relationship("Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Post {self.title}>"


class Comment(db.Model):
    """Comment on a blog post."""

    __tablename__ = "comments"

    id: int = db.Column(db.Integer, primary_key=True)
    content: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)

    author_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<Comment by {self.author.username} on {self.post.title[:20]}>"


# -----------------------------------------------------------------------------
# User Loader for Flask-Login
# -----------------------------------------------------------------------------

@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load a user from the database by ID."""
    return User.query.get(int(user_id))


# -----------------------------------------------------------------------------
# Forms
# -----------------------------------------------------------------------------

class RegistrationForm(FlaskForm):
    """User registration form."""

    username = StringField("Username", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Sign Up")

    def validate_username(self, username: StringField) -> None:
        """Check that the username is not already taken."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError("Username already exists. Please choose a different one.")

    def validate_email(self, email: StringField) -> None:
        """Check that the email is not already registered."""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError("Email already registered. Please use a different one.")


class LoginForm(FlaskForm):
    """User login form."""

    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Create/Edit blog post form."""

    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    content = TextAreaField("Content", validators=[DataRequired()])
    category = SelectMultipleField("Category", coerce=int, validators=[])  # optional
    tags = SelectMultipleField("Tags", coerce=int, validators=[])
    submit = SubmitField("Submit Post")


class CommentForm(FlaskForm):
    """Add comment form."""

    content = TextAreaField("Comment", validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField("Submit Comment")


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def get_categories_and_tags() -> Tuple[List[Category], List[Tag]]:
    """Return all categories and tags for form choices."""
    categories = Category.query.all()
    tags = Tag.query.all()
    return categories, tags


def owner_required(post: Post) -> None:
    """Check if current user is the author or an admin, otherwise abort."""
    if not (current_user.is_admin or post.author == current_user):
        abort(403)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Display a paginated list of all posts."""
    page = request.args.get("page", 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    return render_template("index.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration."""
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
        flash("Your account has been created! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            flash("Login successful!", "success")
            return redirect(next_page) if next_page else redirect(url_for("index"))
        else:
            flash("Login unsuccessful. Please check email and password.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
def logout():
    """Log out the current user."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    """Create a new blog post."""
    categories, tags = get_categories_and_tags()
    form = PostForm()
    form.category.choices = [(c.id, c.name) for c in categories]
    form.tags.choices = [(t.id, t.name) for t in tags]

    if form.validate_on_submit():
        post = Post(
            title=form.title.data,
            content=form.content.data,
            author=current_user,
            category_id=form.category.data[0] if form.category.data else None,
        )
        # Add selected tags
        selected_tags = Tag.query.filter(Tag.id.in_(form.tags.data)).all()
        post.tags.extend(selected_tags)

        db.session.add(post)
        db.session.commit()
        flash("Your post has been created!", "success")
        return redirect(url_for("view_post", post_id=post.id))
    return render_template("create_post.html", form=form, title="New Post")


@app.route("/post/<int:post_id>")
def view_post(post_id: int):
    """Display a single post with its comments."""
    post = Post.query.get_or_404(post_id)
    comment_form = CommentForm()
    return render_template("view_post.html", post=post, comment_form=comment_form)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int):
    """Edit an existing post (author or admin only)."""
    post = Post.query.get_or_404(post_id)
    owner_required(post)

    categories, tags = get_categories_and_tags()
    form = PostForm(obj=post)
    form.category.choices = [(c.id, c.name) for c in categories]
    form.tags.choices = [(t.id, t.name) for t in tags]

    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.category_id = form.category.data[0] if form.category.data else None
        # Update tags
        post.tags = Tag.query.filter(Tag.id.in_(form.tags.data)).all()
        db.session.commit()
        flash("Your post has been updated!", "success")
        return redirect(url_for("view_post", post_id=post.id))

    # Pre-select current category
    if post.category:
        form.category.data = [post.category.id]
    form.tags.data = [tag.id for tag in post.tags]
    return render_template("edit_post.html", form=form, post=post)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id: int):
    """Delete a post (author or admin only)."""
    post = Post.query.get_or_404(post_id)
    owner_required(post)
    db.session.delete(post)
    db.session.commit()
    flash("Your post has been deleted.", "success")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id: int):
    """Add a comment to a post."""
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            content=form.content.data,
            author=current_user,
            post=post,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Your comment has been added.", "success")
    else:
        flash("Comment could not be added. Please check your input.", "danger")
    return redirect(url_for("view_post", post_id=post.id))


@app.route("/category/<int:category_id>")
def posts_by_category(category_id: int):
    """Display posts filtered by category."""
    category = Category.query.get_or_404(category_id)
    page = request.args.get("page", 1, type=int)
    posts = Post.query.filter_by(category=category).order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    return render_template("category.html", category=category, posts=posts)


@app.route("/tag/<int:tag_id>")
def posts_by_tag(tag_id: int):
    """Display posts filtered by tag."""
    tag = Tag.query.get_or_404(tag_id)
    page = request.args.get("page", 1, type=int)
    posts = tag.posts.order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    return render_template("tag.html", tag=tag, posts=posts)


# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors."""
    return render_template("403.html"), 403


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return render_template("500.html"), 500


# -----------------------------------------------------------------------------
# Database Initialization and Main
# -----------------------------------------------------------------------------

def create_tables():
    """Create all database tables if they don't exist."""
    db.create_all()


if __name__ == "__main__":
    create_tables()
    app.run(debug=True)