from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Dict, List

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
app.config["SECRET_KEY"] = "secret_key"

db = SQLAlchemy(app)
login_manager = LoginManager(app)

class User(UserMixin, db.Model):
    """User model."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password: str) -> None:
        """Set user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check user password."""
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    """Blog post model."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author = db.relationship("User", backref=db.backref("posts", lazy=True))
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    category = db.relationship("Category", backref=db.backref("posts", lazy=True))

class Category(db.Model):
    """Post category model."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

class Comment(db.Model):
    """Blog post comment model."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    post = db.relationship("Post", backref=db.backref("comments", lazy=True))
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author = db.relationship("User", backref=db.backref("comments", lazy=True))

@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Load user from database."""
    return User.query.get(int(user_id))

@app.route("/register", methods=["POST"])
def register() -> Dict[str, str]:
    """Register new user."""
    try:
        data = request.json
        user = User(username=data["username"], email=data["email"])
        user.set_password(data["password"])
        db.session.add(user)
        db.session.commit()
        return {"message": "User created successfully"}
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/login", methods=["POST"])
def login() -> Dict[str, str]:
    """Login existing user."""
    try:
        data = request.json
        user = User.query.filter_by(username=data["username"]).first()
        if user and user.check_password(data["password"]):
            login_user(user)
            return {"message": "Logged in successfully"}
        return {"error": "Invalid username or password"}, 401
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/logout", methods=["POST"])
@login_required
def logout() -> Dict[str, str]:
    """Logout current user."""
    logout_user()
    return {"message": "Logged out successfully"}

@app.route("/posts", methods=["GET"])
def get_posts() -> List[Dict[str, str]]:
    """Get all blog posts."""
    posts = Post.query.all()
    return [{"id": str(post.id), "title": post.title, "content": post.content} for post in posts]

@app.route("/posts", methods=["POST"])
@login_required
def create_post() -> Dict[str, str]:
    """Create new blog post."""
    try:
        data = request.json
        post = Post(title=data["title"], content=data["content"], author_id=current_user.id, category_id=data["category_id"])
        db.session.add(post)
        db.session.commit()
        return {"message": "Post created successfully"}
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/posts/<int:post_id>", methods=["GET"])
def get_post(post_id: int) -> Dict[str, str]:
    """Get blog post by ID."""
    post = Post.query.get(post_id)
    if post:
        return {"id": str(post.id), "title": post.title, "content": post.content}
    return {"error": "Post not found"}, 404

@app.route("/posts/<int:post_id>", methods=["PUT"])
@login_required
def update_post(post_id: int) -> Dict[str, str]:
    """Update blog post."""
    try:
        post = Post.query.get(post_id)
        if post and post.author_id == current_user.id:
            data = request.json
            post.title = data["title"]
            post.content = data["content"]
            db.session.commit()
            return {"message": "Post updated successfully"}
        return {"error": "Post not found or not authorized"}, 404
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/posts/<int:post_id>", methods=["DELETE"])
@login_required
def delete_post(post_id: int) -> Dict[str, str]:
    """Delete blog post."""
    try:
        post = Post.query.get(post_id)
        if post and post.author_id == current_user.id:
            db.session.delete(post)
            db.session.commit()
            return {"message": "Post deleted successfully"}
        return {"error": "Post not found or not authorized"}, 404
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/posts/<int:post_id>/comments", methods=["GET"])
def get_comments(post_id: int) -> List[Dict[str, str]]:
    """Get comments for blog post."""
    comments = Comment.query.filter_by(post_id=post_id).all()
    return [{"id": str(comment.id), "content": comment.content} for comment in comments]

@app.route("/posts/<int:post_id>/comments", methods=["POST"])
@login_required
def create_comment(post_id: int) -> Dict[str, str]:
    """Create new comment for blog post."""
    try:
        data = request.json
        comment = Comment(content=data["content"], post_id=post_id, author_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        return {"message": "Comment created successfully"}
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/categories", methods=["GET"])
def get_categories() -> List[Dict[str, str]]:
    """Get all post categories."""
    categories = Category.query.all()
    return [{"id": str(category.id), "name": category.name} for category in categories]

@app.route("/categories", methods=["POST"])
@login_required
def create_category() -> Dict[str, str]:
    """Create new post category."""
    try:
        data = request.json
        category = Category(name=data["name"])
        db.session.add(category)
        db.session.commit()
        return {"message": "Category created successfully"}
    except Exception as e:
        return {"error": str(e)}, 400

if __name__ == "__main__":
    app.run(debug=True)