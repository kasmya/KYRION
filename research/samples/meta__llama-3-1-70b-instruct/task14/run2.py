from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_marshmallow import Marshmallow
from marshmallow import Schema, fields, validates, ValidationError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
db = SQLAlchemy(app)
ma = Marshmallow(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __init__(self, username, password):
        self.username = username
        self.password = generate_password_hash(password)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('posts', lazy=True))
    comments = db.relationship('Comment', backref=db.backref('post', lazy=True))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    post = db.relationship('Post', backref=db.backref('votes', lazy=True))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('votes', lazy=True))
    upvote = db.Column(db.Boolean, nullable=False)

class UserSchema(Schema):
    class Meta:
        fields = ('id', 'username')

class PostSchema(Schema):
    class Meta:
        fields = ('id', 'title', 'content', 'user_id')

class CommentSchema(Schema):
    class Meta:
        fields = ('id', 'content', 'user_id', 'post_id')

class VoteSchema(Schema):
    class Meta:
        fields = ('id', 'post_id', 'user_id', 'upvote')

user_schema = UserSchema()
post_schema = PostSchema()
comment_schema = CommentSchema()
vote_schema = VoteSchema()

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    existing_user = User.query.filter_by(username=data['username']).first()
    if existing_user:
        return jsonify({'error': 'Username already taken'}), 400
    new_user = User(data['username'], data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify(user_schema.dump(new_user)), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not check_password_hash(user.password, data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    session['user_id'] = user.id
    return jsonify(user_schema.dump(user)), 200

@app.route('/posts', methods=['POST'])
def create_post():
    if 'user_id' not in session:
        return jsonify({'error': 'You need to be logged in to create a post'}), 401
    data = request.json
    if 'title' not in data or 'content' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    new_post = Post(title=data['title'], content=data['content'], user_id=session['user_id'])
    db.session.add(new_post)
    db.session.commit()
    return jsonify(post_schema.dump(new_post)), 201

@app.route('/posts/<int:post_id>', methods=['GET', 'PUT', 'DELETE'])
def post(post_id):
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    if request.method == 'GET':
        return jsonify(post_schema.dump(post)), 200
    if request.method == 'PUT':
        data = request.json
        if 'title' in data:
            post.title = data['title']
        if 'content' in data:
            post.content = data['content']
        db.session.commit()
        return jsonify(post_schema.dump(post)), 200
    if request.method == 'DELETE':
        db.session.delete(post)
        db.session.commit()
        return jsonify({'message': 'Post deleted'}), 200

@app.route('/posts/<int:post_id>/comments', methods=['POST'])
def create_comment(post_id):
    if 'user_id' not in session:
        return jsonify({'error': 'You need to be logged in to comment'}), 401
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    data = request.json
    if 'content' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    new_comment = Comment(content=data['content'], user_id=session['user_id'], post_id=post_id)
    db.session.add(new_comment)
    db.session.commit()
    return jsonify(comment_schema.dump(new_comment)), 201

@app.route('/posts/<int:post_id>/votes', methods=['POST'])
def vote(post_id):
    if 'user_id' not in session:
        return jsonify({'error': 'You need to be logged in to vote'}), 401
    post = Post.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    data = request.json
    if 'upvote' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    existing_vote = Vote.query.filter_by(user_id=session['user_id'], post_id=post_id).first()
    if existing_vote:
        if existing_vote.upvote == data['upvote']:
            db.session.delete(existing_vote)
            db.session.commit()
            return jsonify({'message': 'Vote removed'}), 200
        else:
            existing_vote.upvote = data['upvote']
            db.session.commit()
            return jsonify({'message': 'Vote updated'}), 200
    new_vote = Vote(post_id=post_id, user_id=session['user_id'], upvote=data['upvote'])
    db.session.add(new_vote)
    db.session.commit()
    return jsonify(vote_schema.dump(new_vote)), 201

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'Missing query parameter'}), 400
    results = Post.query.filter(Post.title.contains(query) | Post.content.contains(query)).all()
    return jsonify([post_schema.dump(post) for post in results]), 200

if __name__ == '__main__':
    app.run(debug=True)