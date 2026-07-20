from flask import Flask, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from hashlib import sha256
from typing import Dict, List, Optional

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forum.db"
app.config["SECRET_KEY"] = "mysecretkey"
db = SQLAlchemy(app)


class User(db.Model):
    """Forum User Model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    posts = db.relationship("Post", backref="author", lazy=True)
    comments = db.relationship("Comment", backref="author", lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"

    def set_password(self, password: str) -> None:
        """Hash password before storing"""
        self.password = sha256(password.encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash"""
        return self.password == sha256(password.encode()).hexdigest()


class Post(db.Model):
    """Forum Post Model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    comments = db.relationship("Comment", backref="post", lazy=True)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Post {self.title}>"


class Comment(db.Model):
    """Forum Comment Model"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def __repr__(self):
        return f"<Comment {self.content[:20]}...>"


# Routing

@app.route('/')
def index():
    """Redirect to login if not authenticated, else show posts"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    posts = Post.query.all()
    return jsonify([{"id": p.id, "title": p.title, "author": p.author.username} for p in posts])


@app.route('/register', methods=['POST'])
def register():
    """Handle User Registration"""
    data: Dict = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 400
    
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Username already exists"}), 400
    
    user = User(username=data["username"])
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created successfully"})


@app.route('/login', methods=['POST'])
def login():
    """Handle User Login"""
    data: Dict = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 400
    
    user = User.query.filter_by(username=data["username"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid username or password"}), 401
    
    session['user_id'] = user.id
    return jsonify({"message": "Logged in successfully"})


@app.route('/logout')
def logout():
    """Logout User"""
    session.pop('user_id', None)
    return jsonify({"message": "Logged out"})


@app.route('/posts', methods=['POST'])
def create_post():
    """Create New Post"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    data: Dict = request.get_json()
    if not data or "title" not in data or "content" not in data:
        return jsonify({"error": "Missing title or content"}), 400
    
    post = Post(title=data["title"], content=data["content"], user_id=session['user_id'])
    db.session.add(post)
    db.session.commit()
    return jsonify({"message": "Post created", "post_id": post.id})


@app.route('/posts/<int:post_id>', methods=['PUT', 'DELETE'])
def manage_post(post_id: int):
    """Edit or Delete Post"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    
    if post.author.id != session['user_id']:
        return jsonify({"error": "Not authorized"}), 403
    
    if request.method == 'PUT':
        data: Dict = request.get_json()
        if "title" in data:
            post.title = data["title"]
        if "content" in data:
            post.content = data["content"]
        db.session.commit()
        return jsonify({"message": "Post updated"})
    elif request.method == 'DELETE':
        db.session.delete(post)
        db.session.commit()
        return jsonify({"message": "Post deleted"})

    return jsonify({"error": "Invalid request method"}), 405


@app.route('/posts/<int:post_id>/comments', methods=['POST'])
def create_comment(post_id: int):
    """Create Comment on Post"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    
    data: Dict = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Missing comment content"}), 400
    
    comment = Comment(content=data["content"], post_id=post_id, user_id=session['user_id'])
    db.session.add(comment)
    db.session.commit()
    return jsonify({"message": "Comment created"})


@app.route('/posts/<int:post_id>/vote', methods=['PUT'])
def vote_post(post_id: int, direction: Optional[str] = None):
    """Upvote or Downvote Post"""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    
    data: Dict = request.get_json()
    if "direction" not in data or data["direction"] not in ["up", "down"]:
        return jsonify({"error": "Invalid vote direction"}), 400
    
    direction = data["direction"]
    if direction == "up":
        post.upvotes += 1
    else:
        post.downvotes += 1
    db.session.commit()
    return jsonify({"message": f"Post {direction}voted", "upvotes": post.upvotes, "downvotes": post.downvotes})


@app.route('/search', methods=['GET'])
def search_posts():
    """Search Posts by Title or Content"""
    query = request.args.get("query")
    if not query:
        return jsonify({"error": "Missing search query"}), 400
    
    posts = Post.query.filter(
        db.or_(Post.title.like(f"%{query}%"), Post.content.like(f"%{query}%"))
    ).all()
    return jsonify([{"id": p.id, "title": p.title, "content": p.content[:100]} for p in posts])


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)