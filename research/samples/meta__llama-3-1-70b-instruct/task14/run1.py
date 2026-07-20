from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forum.db"
db = SQLAlchemy(app)


class User(db.Model):
    """User model."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    posts = db.relationship("Post", backref="author", lazy=True)
    comments = db.relationship("Comment", backref="author", lazy=True)

    def __init__(self, username: str, password: str) -> None:
        """Initialize a new user."""
        self.username = username
        self.password = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if the provided password is correct."""
        return check_password_hash(self.password, password)


class Post(db.Model):
    """Post model."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    comments = db.relationship("Comment", backref="post", lazy=True)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)

    def __init__(self, title: str, content: str, author: User) -> None:
        """Initialize a new post."""
        self.title = title
        self.content = content
        self.author = author


class Comment(db.Model):
    """Comment model."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def __init__(self, content: str, post: Post, author: User) -> None:
        """Initialize a new comment."""
        self.content = content
        self.post = post
        self.author = author


@app.route("/")
def index() -> str:
    """Render the index page."""
    posts = Post.query.all()
    return render_template("index.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register() -> Optional[str]:
    """Handle user registration."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user is None:
            new_user = User(username, password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login"))
        else:
            flash("Username already exists")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> Optional[str]:
    """Handle user login."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user is not None and user.check_password(password):
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password")
    return render_template("login.html")


@app.route("/create_post", methods=["GET", "POST"])
def create_post() -> Optional[str]:
    """Handle post creation."""
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        author = User.query.filter_by(username=request.form["author"]).first()
        if author is not None:
            new_post = Post(title, content, author)
            db.session.add(new_post)
            db.session.commit()
            return redirect(url_for("index"))
        else:
            flash("Invalid author")
    return render_template("create_post.html")


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def post(post_id: int) -> str:
    """Render a post page."""
    post = Post.query.get(post_id)
    if post is None:
        return "Post not found", 404
    if request.method == "POST":
        if request.form["action"] == "comment":
            content = request.form["content"]
            author = User.query.filter_by(username=request.form["author"]).first()
            if author is not None:
                new_comment = Comment(content, post, author)
                db.session.add(new_comment)
                db.session.commit()
        elif request.form["action"] == "upvote":
            post.upvotes += 1
            db.session.commit()
        elif request.form["action"] == "downvote":
            post.downvotes += 1
            db.session.commit()
    comments = Comment.query.filter_by(post_id=post_id).all()
    return render_template("post.html", post=post, comments=comments)


@app.route("/edit_post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id: int) -> Optional[str]:
    """Handle post editing."""
    post = Post.query.get(post_id)
    if post is None:
        return "Post not found", 404
    if request.method == "POST":
        post.title = request.form["title"]
        post.content = request.form["content"]
        db.session.commit()
        return redirect(url_for("post", post_id=post_id))
    return render_template("edit_post.html", post=post)


@app.route("/delete_post/<int:post_id>")
def delete_post(post_id: int) -> str:
    """Handle post deletion."""
    post = Post.query.get(post_id)
    if post is not None:
        db.session.delete(post)
        db.session.commit()
    return redirect(url_for("index"))


@app.route("/search", methods=["GET", "POST"])
def search() -> str:
    """Handle search functionality."""
    if request.method == "POST":
        query = request.form["query"]
        posts = Post.query.filter(Post.title.like(f"%{query}%")).all()
        return render_template("search.html", posts=posts)
    return render_template("search.html")


if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)