from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from typing import List, Dict

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
app.config["SECRET_KEY"] = "secret"  # Replace with a secure secret key
db = SQLAlchemy(app)
login_manager = LoginManager(app)


class User(UserMixin, db.Model):
    """Represents a user with authentication capabilities."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password: str) -> None:
        """Sets the user's password after hashing."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Checks if the provided password matches the hashed password."""
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    """Represents a blog post with title, content, categories, and tags."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("posts", lazy=True))
    categories = db.relationship("Category", secondary="post_categories", backref=db.backref("posts", lazy=True))
    tags = db.relationship("Tag", secondary="post_tags", backref=db.backref("posts", lazy=True))

    def to_dict(self) -> Dict:
        """Returns a dictionary representation of the post."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "username": self.user.username,
            "categories": [cat.name for cat in self.categories],
            "tags": [tag.name for tag in self.tags]
        }


class Category(db.Model):
    """Represents a category for posts."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Tag(db.Model):
    """Represents a tag for posts."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


post_categories = db.Table("post_categories",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("category.id"), primary_key=True)
)


post_tags = db.Table("post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True)
)


class Comment(db.Model):
    """Represents a comment on a post."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    post = db.relationship("Post", backref=db.backref("comments", lazy=True))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("comments", lazy=True))

    def to_dict(self) -> Dict:
        """Returns a dictionary representation of the comment."""
        return {
            "id": self.id,
            "content": self.content,
            "username": self.user.username
        }


@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Loads a user instance based on the user ID."""
    return User.query.get(int(user_id))


@app.route("/login", methods=["POST"])
def login() -> str:
    """Handles user login."""
    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 401
    
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid username or password"}), 401
    
    login_user(user)
    return jsonify({"message": "Logged in successfully"})


@app.route("/logout")
@login_required
def logout() -> str:
    """Logs out the current user."""
    logout_user()
    return jsonify({"message": "Logged out successfully"})


@app.route("/register", methods=["POST"])
def register() -> str:
    """Registers a new user."""
    data = request.get_json()
    if not data or "username" not in data or "email" not in data or "password" not in data:
        return jsonify({"error": "Missing required fields"}), 400
    
    user = User.query.filter_by(username=data["username"]).first()
    if user:
        return jsonify({"error": "Username already exists"}), 400
    
    new_user = User(username=data["username"], email=data["email"])
    new_user.set_password(data["password"])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User created successfully"})


@app.route("/posts", methods=["GET", "POST"])
@login_required
def manage_posts() -> str:
    """Creates or retrieves posts based on the request method."""
    if request.method == "POST":
        data = request.get_json()
        if not data or "title" not in data or "content" not in data:
            return jsonify({"error": "Missing title or content"}), 400
        
        new_post = Post(title=data["title"], content=data["content"], user=current_user)
        if "categories" in data:
            new_post.categories = [Category.query.filter_by(name-cat).first() or Category(name=cat) for cat in data["categories"]]
        if "tags" in data:
            new_post.tags = [Tag.query.filter_by(name=tag).first() or Tag(name=tag) for tag in data["tags"]]
        
        db.session.add(new_post)
        db.session.commit()
        return jsonify(new_post.to_dict()), 201
    
    posts = Post.query.all()
    return jsonify([post.to_dict() for post in posts])


@app.route("/posts/<int:post_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def manage_post(post_id: int) -> str:
    """Retrieves, updates, or deletes a post based on the request method."""
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    
    if request.method == "PUT":
        data = request.get_json()
        if "title" in data:
            post.title = data["title"]
        if "content" in data:
            post.content = data["content"]
        if "categories" in data:
            post.categories = [Category.query.filter_by(name=cat).first() or Category(name=cat) for cat in data["categories"]]
        if "tags" in data:
            post.tags = [Tag.query.filter_by(name=tag).first() or Tag(name=tag) for tag in data["tags"]]
        db.session.commit()
        return jsonify(post.to_dict())
    
    elif request.method == "DELETE":
        db.session.delete(post)
        db.session.commit()
        return jsonify({"message": "Post deleted successfully"})
    
    return jsonify(post.to_dict())


@app.route("/posts/<int:post_id>/comments", methods=["POST", "GET"])
@login_required
def manage_comments(post_id: int) -> str:
    """Creates or retrieves comments for a post based on the request method."""
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    
    if request.method == "POST":
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "Missing comment content"}), 400
        
        new_comment = Comment(content=data["content"], post=post, user=current_user)
        db.session.add(new_comment)
        db.session.commit()
        return jsonify(new_comment.to_dict()), 201
    
    comments = post.comments.all()
    return jsonify([comment.to_dict() for comment in comments])


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)