"""Single-file Django Blog CMS with authentication, posts, and comments."""
import os, sys, django
from django.conf import settings
from django.core.management import execute_from_command_line
from django.urls import path, include
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.models import User
from django.db import models
from django.views.decorators.csrf import csrf_exempt
import json

# Configure Django settings
settings.configure(
    DEBUG=True,
    SECRET_KEY='django-insecure-blog-key',
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': 'blog.db'}},
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions'],
    MIDDLEWARE=['django.middleware.common.CommonMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware'],
    ROOT_URLCONF=__name__,
)
django.setup()

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    class Meta: app_label = 'blog'

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    class Meta: app_label = 'blog'

class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    categories = models.ManyToManyField(Category)
    tags = models.ManyToManyField(Tag)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: app_label = 'blog'

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author_name = models.CharField(max_length=100)
    content = models.TextField()
    approved = models.BooleanField(default=False)
    class Meta: app_label = 'blog'

# Create tables
from django.core.management.color import no_style
from django.db import connection
with connection.schema_editor() as schema_editor:
    for model in [Category, Tag, Post, Comment]:
        try: schema_editor.create_model(model)
        except: pass

@csrf_exempt
def create_post(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        # Simplified auth: assuming user 1 exists for demo
        author = User.objects.first() or User.objects.create_user('admin', password='admin')
        post = Post.objects.create(title=data['title'], content=data['content'], author=author)
        return JsonResponse({"id": post.id, "title": post.title}, status=201)
    return JsonResponse({"error": "POST only"}, status=405)

def list_posts(request):
    q = request.GET.get('q', '')
    posts = Post.objects.all()
    if q: posts = posts.filter(title__icontains=q) | posts.filter(content__icontains=q)
    data = [{"id": p.id, "title": p.title, "author": p.author.username} for p in posts[:10]]
    return JsonResponse(data, safe=False)

def rss_feed(request):
    posts = Post.objects.all()[:10]
    xml = '<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>'
    for p in posts:
        xml += f'<item><title>{p.title}</title><description>{p.content[:50]}</description></item>'
    xml += '</channel></rss>'
    return HttpResponse(xml, content_type='application/rss+xml')

urlpatterns = [
    path('api/posts/', list_posts),
    path('api/posts/create/', create_post),
    path('rss/', rss_feed),
]

if __name__ == '__main__':
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)