from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import InputRequired, Email, Length, EqualTo

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    """User model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Check if password is correct"""
        return check_password_hash(self.password, password)

class Post(db.Model):
    """Post model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Comment(db.Model):
    """Comment model"""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class LoginForm(FlaskForm):
    """Login form"""
    email = StringField('Email', validators=[InputRequired(), Email()])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=8)])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    """Register form"""
    username = StringField('Username', validators=[InputRequired(), Length(min=4)])
    email = StringField('Email', validators=[InputRequired(), Email()])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class PostForm(FlaskForm):
    """Post form"""
    title = StringField('Title', validators=[InputRequired(), Length(min=4)])
    content = TextAreaField('Content', validators=[InputRequired()])
    category = StringField('Category', validators=[InputRequired(), Length(min=4)])
    submit = SubmitField('Create Post')

class CommentForm(FlaskForm):
    """Comment form"""
    content = TextAreaField('Content', validators=[InputRequired()])
    submit = SubmitField('Comment')

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    """Load user"""
    return User.query.get(int(user_id))

@app.route('/')
def index():
    """Index page"""
    posts = Post.query.all()
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register page"""
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(form.username.data, form.email.data, form.password.data)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/post/<int:post_id>')
def post(post_id):
    """Post page"""
    post = Post.query.get_or_404(post_id)
    comments = Comment.query.filter_by(post_id=post_id).all()
    return render_template('post.html', post=post, comments=comments)

@app.route('/post/<int:post_id>/comment', methods=['GET', 'POST'])
@login_required
def comment(post_id):
    """Comment page"""
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(content=form.content.data, post_id=post_id, user_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for('post', post_id=post_id))
    return render_template('comment.html', form=form)

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    """Create post page"""
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, category=form.category.data, user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('create_post.html', form=form)

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    """Edit post page"""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        return 'You are not authorized to edit this post'
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.category = form.category.data
        db.session.commit()
        return redirect(url_for('post', post_id=post_id))
    return render_template('edit_post.html', form=form, post=post)

@app.route('/post/<int:post_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_post(post_id):
    """Delete post page"""
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        return 'You are not authorized to delete this post'
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    """Logout page"""
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)