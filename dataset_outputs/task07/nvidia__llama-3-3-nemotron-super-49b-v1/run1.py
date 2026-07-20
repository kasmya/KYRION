# Import necessary libraries
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from hashlib import sha256
from typing import Dict, List, Optional
from dataclasses import dataclass

# Initialize the Flask app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
app.config["SECRET_KEY"] = "your-secret-key-here"

# Initialize the SQLAlchemy ORM
db = SQLAlchemy(app)


# Define data models
@dataclass
class User(db.Model):
    """User model with authentication."""
    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(120), nullable=False)

    def set_password(self, password: str) -> None:
        """Set user password with hashing."""
        self.password_hash = sha256(password.encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        """Verify user password."""
        return self.password_hash == sha256(password.encode()).hexdigest()


@dataclass
class Post(db.Model):
    """Blog post model."""
    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(120), nullable=False)
    content: str = db.Column(db.Text, nullable=False)
    author_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author: User = db.relationship("User", backref=db.backref("posts", lazy=True))
    category: str = db.Column(db.String(80), nullable=False)
    tags: List[str] = db.Column(db.JSON, default=[])


@dataclass
class Comment(db.Model):
    """Comment model for posts."""
    id: int = db.Column(db.Integer, primary_key=True)
    content: str = db.Column(db.Text, nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    post: Post = db.relationship("Post", backref=db.backref("comments", lazy=True))
    author_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author: User = db.relationship("User", backref=db.backref("comments", lazy=True))


# Authentication routes
@app.route("/login", methods=["POST"])
def login() -> Dict[str, str]:
    """Login endpoint."""
    data: Dict[str, str] = request.json
    user: Optional[User] = User.query.filter_by(username=data["username"]).first()
    if user and user.check_password(data["password"]):
        session["user_id"] = user.id
        return {"message": "Logged in successfully"}
    return {"error": "Invalid credentials"}, 401


@app.route("/register", methods=["POST"])
def register() -> Dict[str, str]:
    """Register new user."""
    data: Dict[str, str] = request.json
    if User.query.filter_by(username=data["username"]).first():
        return {"error": "Username already exists"}, 400
    new_user = User(username=data["username"])
    new_user.set_password(data["password"])
    db.session.add(new_user)
    db.session.commit()
    return {"message": "User created successfully"}


# Post CRUD routes
@app.route("/posts", methods=["GET"])
def get_posts() -> List[Dict[str, str]]:
    """Fetch all blog posts."""
    posts: List[Post] = Post.query.all()
    return [{"id": p.id, "title": p.title, "author": p.author.username} for p in posts]


@app.route("/posts", methods=["POST"])
def create_post() -> Dict[str, str]:
    """Create a new blog post."""
    if "user_id" not in session:
        return {"error": "Unauthorized"}, 401
    data: Dict[str, str] = request.json
    new_post = Post(title=data["title"], content=data["content"], author_id=session["user_id"], category=data["category"], tags=data["tags"])
    db.session.add(new_post)
    db.session.commit()
    return {"message": "Post created successfully"}


@app.route("/posts/<int:post_id>", methods=["GET"])
def get_post(post_id: int) -> Dict[str, str]:
    """Fetch a single post by ID."""
    post: Optional[Post] = Post.query.get(post_id)
    if not post:
        return {"error": "Post not found"}, 404
    return {"id": post.id, "title": post.title, "content": post.content, "author": post.author.username}


@app.route("/posts/<int:post_id>", methods=["PUT"])
def update_post(post_id: int) -> Dict[str, str]:
    """Update an existing post."""
    if "user_id" not in session:
        return {"error": "Unauthorized"}, 401
    post: Optional[Post] = Post.query.get(post_id)
    if not post or post.author_id != session["user_id"]:
        return {"error": "Forbidden"}, 403
    data: Dict[str, str] = request.json
    post.title = data["title"]
    post.content = data["content"]
    db.session.commit()
    return {"message": "Post updated successfully"}


@app.route("/posts/<int:post_id>", methods=["DELETE"])
def delete_post(post_id: int) -> Dict[str, str]:
    """Delete a post."""
    if "user_id" not in session:
        return {"error": "Unauthorized"}, 401
    post: Optional[Post] = Post.query.get(post_id)
    if not post or post.author_id != session["user_id"]:
        return {"error": "Forbidden"}, 403
    db.session.delete(post)
    db.session.commit()
    return {"message": "Post deleted successfully"}


# Comment routes
@app.route("/posts/<int:post_id>/comments", methods=["POST"])
def create_comment(post_id: int) -> Dict[str, str]:
    """Create a new comment on a post."""
    if "user_id" not in session:
        return {"error": "Unauthorized"}, 401
    post: Optional[Post] = Post.query.get(post_id)
    if not post:
        return {"error": "Post not found"}, 404
    data: Dict[str, str] = request.json
    new_comment = Comment(content=data["content"], post_id=post_id, author_id=session["user_id"])
    db.session.add(new_comment)
    db.session.commit()
    return {"message": "Comment created successfully"}


@app.route("/posts/<int:post_id>/comments", methods=["GET"])
def get_comments(post_id: int) -> List[Dict[str, str]]:
    """Fetch all comments for a post."""
    post: Optional[Post] = Post.query.get(post_id)
    if not post:
        return {"error": "Post not found"}, 404
    comments: List[Comment] = post.comments
    return [{"id": c.id, "content": c.content, "author": c.author.username} for c in comments]


# Category/Tag filtering
@app.route("/posts/by-category/<string:category>", methods=["GET"])
def get_posts_by_category(category: str) -> List[Dict[str, str]]:
    """Fetch posts by category."""
    posts: List[Post] = Post.query.filter_by(category=category).all()
    return [{"id": p.id, "title": p.title, "author": p.author.username} for p in posts]


@app.route("/posts/by-tag/<string:tag>", methods=["GET"])
def get_posts_by_tag(tag: str) -> List[Dict[str, str]]:
    """Fetch posts by tag."""
    posts: List[Post] = Post.query.filter(Post.tags.contains([tag])).all()
    return [{"id": p.id, "title": p.title, "author": p.author.username} for p in posts]


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)