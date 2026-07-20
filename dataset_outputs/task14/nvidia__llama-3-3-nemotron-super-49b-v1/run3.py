# forum.py
from flask import Flask, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from typing import List, Dict

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret_key_here"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forum.db"
db = SQLAlchemy(app)
login_manager = LoginManager(app)

class User(UserMixin, db.Model):
    """User Model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    posts = db.relationship("Post", backref="author", lazy=True)
    comments = db.relationship("Comment", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        """Set user password with hashing"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check user password"""
        return check_password_hash(self.password_hash, password)

class Post(db.Model):
    """Post Model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    comments = db.relationship("Comment", backref="post", lazy=True)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)

class Comment(db.Model):
    """Comment Model"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Load user from session"""
    return User.query.get(int(user_id))

# Registration
@app.route("/register", methods=["POST"])
def register() -> Dict[str, str]:
    """Register new user"""
    data = request.json
    if not data.get("username") or not data.get("email") or not data.get("password"):
        return {"error": "Missing required fields"}, 400
    if User.query.filter_by(username=data["username"]).first():
        return {"error": "Username already exists"}, 400
    if User.query.filter_by(email=data["email"]).first():
        return {"error": "Email already exists"}, 400
    
    user = User(username=data["username"], email=data["email"])
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return {"message": "User created successfully"}

# Login
@app.route("/login", methods=["POST"])
def login() -> Dict[str, str]:
    """Login existing user"""
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not user.check_password(data["password"]):
        return {"error": "Invalid username or password"}, 401
    login_user(user)
    return {"message": "Logged in successfully"}

# Logout
@app.route("/logout")
@login_required
def logout() -> Dict[str, str]:
    """Logout current user"""
    logout_user()
    return {"message": "Logged out successfully"}

# Create Post
@app.route("/posts", methods=["POST"])
@login_required
def create_post() -> Dict[str, str]:
    """Create new post"""
    data = request.json
    if not data.get("title") or not data.get("content"):
        return {"error": "Missing required fields"}, 400
    post = Post(title=data["title"], content=data["content"], user_id=current_user.id)
    db.session.add(post)
    db.session.commit()
    return {"message": "Post created successfully"}

# Get Posts
@app.route("/posts", methods=["GET"])
def get_posts() -> List[Dict[str, str]]:
    """Get all posts"""
    posts = Post.query.all()
    return [{"id": p.id, "title": p.title, "content": p.content, "author": p.author.username} for p in posts]

# Edit Post
@app.route("/posts/<int:post_id>", methods=["PUT"])
@login_required
def edit_post(post_id: int) -> Dict[str, str]:
    """Edit existing post"""
    post = Post.query.get(post_id)
    if not post or post.author.id != current_user.id:
        return {"error": "Post not found or not yours"}, 403
    data = request.json
    if data.get("title"):
        post.title = data["title"]
    if data.get("content"):
        post.content = data["content"]
    db.session.commit()
    return {"message": "Post updated successfully"}

# Delete Post
@app.route("/posts/<int:post_id>", methods=["DELETE"])
@login_required
def delete_post(post_id: int) -> Dict[str, str]:
    """Delete post"""
    post = Post.query.get(post_id)
    if not post or post.author.id != current_user.id:
        return {"error": "Post not found or not yours"}, 403
    db.session.delete(post)
    db.session.commit()
    return {"message": "Post deleted successfully"}

# Comment on Post
@app.route("/posts/<int:post_id>/comments", methods=["POST"])
@login_required
def create_comment(post_id: int) -> Dict[str, str]:
    """Create comment on post"""
    post = Post.query.get(post_id)
    if not post:
        return {"error": "Post not found"}, 404
    data = request.json
    if not data.get("content"):
        return {"error": "Missing required fields"}, 400
    comment = Comment(content=data["content"], post_id=post_id, user_id=current_user.id)
    db.session.add(comment)
    db.session.commit()
    return {"message": "Comment created successfully"}

# Upvote/Downvote Post
@app.route("/posts/<int:post_id>/vote", methods=["PUT"])
@login_required
def vote_post(post_id: int) -> Dict[str, str]:
    """Vote on post"""
    post = Post.query.get(post_id)
    if not post:
        return {"error": "Post not found"}, 404
    data = request.json
    if data.get("vote") == "up":
        post.upvotes += 1
    elif data.get("vote") == "down":
        post.downvotes += 1
    else:
        return {"error": "Invalid vote type"}, 400
    db.session.commit()
    return {"message": "Vote registered successfully"}

# Search Posts
@app.route("/search", methods=["GET"])
def search_posts() -> List[Dict[str, str]]:
    """Search posts by title or content"""
    query = request.args.get("q")
    if not query:
        return {"error": "Missing query parameter"}, 400
    posts = Post.query.filter((Post.title.like(f"%{query}%")) | (Post.content.like(f"%{query}%"))).all()
    return [{"id": p.id, "title": p.title, "content": p.content, "author": p.author.username} for p in posts]

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)