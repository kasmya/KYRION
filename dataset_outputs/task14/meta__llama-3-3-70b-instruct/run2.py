from flask import Flask, render_template, request, redirect, url_for, session, flash
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
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password: str) -> None:
        """Set user password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check user password."""
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    """Post model."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("posts", lazy=True))
    comments = db.relationship("Comment", backref=db.backref("post", lazy=True))
    upvotes = db.relationship("Upvote", backref=db.backref("post", lazy=True))
    downvotes = db.relationship("Downvote", backref=db.backref("post", lazy=True))


class Comment(db.Model):
    """Comment model."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User", backref=db.backref("comments", lazy=True))


class Upvote(db.Model):
    """Upvote model."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Downvote(db.Model):
    """Downvote model."""
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


@app.route("/register", methods=["GET", "POST"])
def register() -> Optional[str]:
    """Register a new user."""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user:
            flash("Username already exists.")
            return redirect(url_for("register"))
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful.")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> Optional[str]:
    """Login a user."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Login successful.")
            return redirect(url_for("index"))
        flash("Invalid username or password.")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout() -> Optional[str]:
    """Logout a user."""
    session.pop("user_id", None)
    flash("Logout successful.")
    return redirect(url_for("index"))


@app.route("/")
def index() -> str:
    """Show all posts."""
    posts = Post.query.all()
    return render_template("index.html", posts=posts)


@app.route("/post/<int:post_id>")
def post(post_id: int) -> str:
    """Show a post."""
    post = Post.query.get_or_404(post_id)
    comments = Comment.query.filter_by(post_id=post_id).all()
    return render_template("post.html", post=post, comments=comments)


@app.route("/post/<int:post_id>/comment", methods=["POST"])
def comment(post_id: int) -> Optional[str]:
    """Comment on a post."""
    if "user_id" not in session:
        flash("You must be logged in to comment.")
        return redirect(url_for("post", post_id=post_id))
    content = request.form["content"]
    new_comment = Comment(content=content, post_id=post_id, user_id=session["user_id"])
    db.session.add(new_comment)
    db.session.commit()
    flash("Comment added successfully.")
    return redirect(url_for("post", post_id=post_id))


@app.route("/post/<int:post_id>/upvote")
def upvote(post_id: int) -> Optional[str]:
    """Upvote a post."""
    if "user_id" not in session:
        flash("You must be logged in to upvote.")
        return redirect(url_for("post", post_id=post_id))
    post = Post.query.get_or_404(post_id)
    upvote = Upvote.query.filter_by(post_id=post_id, user_id=session["user_id"]).first()
    if upvote:
        flash("You have already upvoted this post.")
        return redirect(url_for("post", post_id=post_id))
    new_upvote = Upvote(post_id=post_id, user_id=session["user_id"])
    db.session.add(new_upvote)
    db.session.commit()
    flash("Upvote added successfully.")
    return redirect(url_for("post", post_id=post_id))


@app.route("/post/<int:post_id>/downvote")
def downvote(post_id: int) -> Optional[str]:
    """Downvote a post."""
    if "user_id" not in session:
        flash("You must be logged in to downvote.")
        return redirect(url_for("post", post_id=post_id))
    post = Post.query.get_or_404(post_id)
    downvote = Downvote.query.filter_by(post_id=post_id, user_id=session["user_id"]).first()
    if downvote:
        flash("You have already downvoted this post.")
        return redirect(url_for("post", post_id=post_id))
    new_downvote = Downvote(post_id=post_id, user_id=session["user_id"])
    db.session.add(new_downvote)
    db.session.commit()
    flash("Downvote added successfully.")
    return redirect(url_for("post", post_id=post_id))


@app.route("/search", methods=["GET", "POST"])
def search() -> str:
    """Search for posts."""
    if request.method == "POST":
        query = request.form["query"]
        posts = Post.query.filter(Post.title.like(f"%{query}%")).all()
        return render_template("search.html", posts=posts, query=query)
    return render_template("search.html")


@app.errorhandler(404)
def page_not_found(e) -> str:
    """404 error handler."""
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(e) -> str:
    """500 error handler."""
    return render_template("500.html"), 500


if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)