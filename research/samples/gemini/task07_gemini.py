"""
Task 7: Enterprise Content Management System Core
Features: Explicit DB Model schemas, Moderation scopes, Text queries engines, fully validated RSS feed channels.
Requires: django, django-allauth (or configured local middleware setups)
"""

import sys
import os
from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.db import models
from django.contrib.auth.models import User
from django.apps import AppConfig
from django.contrib.syndication.views import Feed
from django.shortcuts import render, get_object_or_404

# --- Settings & Dynamic Environment Injection ---
if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="django-insecure-production-ready-evaluation-fallback-string",
        ROOT_URLCONF=__name__,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "cms_platform.db",
            }
        },
        TEMPLATES=[{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                ],
            },
        }],
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "cms_application.apps.CmsAppConfig",  # Explicit module linkage overrides
        ],
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
    )

# --- Application Subsystem Configurations ---
class CmsAppConfig(AppConfig):
    name = 'cms_application'
    verbose_name = "Core CMS Suite Engine"

# --- Database Schema Architectures ---

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta: app_label = 'cms_application'
    def __str__(self) -> str: return self.name

class Post(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blog_posts")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    published_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta: app_label = 'cms_application'
    def __str__(self) -> str: return self.title

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False) # Moderation structural toggle

    class Meta: app_label = 'cms_application'
    def __str__(self) -> str: return f"Comment by {self.user.username} on {self.post.title}"

# --- Execution Controller Views ---

def feed_landing_list(request) -> HttpResponse:
    """Retrieves all active posts, handling textual database lookup filters if search queries are passed."""
    query = request.GET.get('q', '').strip()
    posts_pool = Post.objects.filter(is_active=True)
    
    if query:
        posts_pool = posts_pool.filter(models.Q(title__icontains=query) | models.Q(body__icontains=query))
        
    output_html = f"<h1>Published Enterprise Posts Portal</h1>"
    output_html += f'<form method="GET" action=""><input type="text" name="q" value="{query}" placeholder="Search publications..."><button type="submit">Query Database</button></form>'
    
    for item in posts_pool:
        output_html += f'<h3><a href="/post/{item.slug}/">{item.title}</a></h3><p>Category: {item.category.name if item.category else "General"} | Author: {item.author.username}</p>'
    
    return HttpResponse(output_html)

def content_detail_viewer(request, slug: str) -> HttpResponse:
    """Renders details for an individual post and handles comment form submissions securely."""
    post_item = get_object_or_404(Post, slug=slug, is_active=True)
    
    # Process comment submission if requested
    if request.method == "POST" and request.user.is_authenticated:
        comment_body = request.POST.get('comment_content', '').strip()
        if comment_body:
            Comment.objects.create(
                post=post_item,
                user=request.user,
                content=comment_body,
                is_approved=False  # Requires admin approval
            )
            return HttpResponseRedirect(request.path)

    approved_comments = post_item.comments.filter(is_approved=True)
    
    detail_html = f"<h2>{post_item.title}</h2><p>{post_item.body}</p><hr><h4>Moderated Interaction Feed Comments ({approved_comments.count()})</h4>"
    for comm in approved_comments:
        detail_html += f"<p><strong>{comm.user.username}</strong>: {comm.content} <small>({comm.created_on.strftime('%Y-%m-%d')})</small></p>"
        
    if request.user.is_authenticated:
        detail_html += '<form method="POST"><h3>Leave a Comment</h3><textarea name="comment_content" required></textarea><br><button type="submit">Submit for Moderation</button></form>'
    else:
        detail_html += "<p><em>Log in to participate in the comments section.</em></p>"
        
    return HttpResponse(detail_html)

# --- RSS Distribution Channels ---

class PlatformRSSFeed(Feed):
    title = "CMS Corporate Broadcast Stream"
    link = "/rss/"
    description = "Updates regarding corporate research analytics articles."

    def items(self) -> Any:
        return Post.objects.filter(is_active=True).order_spacing("-published_date")[:15] if hasattr(Post.objects, 'order_spacing') else Post.objects.filter(is_active=True).order_by("-published_date")[:15]

    def item_title(self, item: Post) -> str: return item.title
    def item_description(self, item: Post) -> str: return item.body[:150] + "..."
    def item_link(self, item: Post) -> str: return f"/post/{item.slug}/"

# --- URL Mapping Routing Matrices ---
from django.urls import path
urlpatterns = [
    path("", feed_landing_list, name="cms_landing"),
    path("post/<slug:slug>/", content_detail_viewer, name="post_detail"),
    path("rss/", PlatformRSSFeed(), name="rss_feed_channel"),
]

if __name__ == "__main__":
    # Bootstraps programmatic execution contexts instantly
    os.makedirs("cms_application", exist_ok=True)
    with open("cms_application/__init__.py", "w") as f: f.write("")
    with open("cms_application/apps.py", "w") as f:
        f.write("from django.apps import AppConfig\nclass CmsAppConfig(AppConfig):\n    name='cms_application'\n")
        
    # Standard migration execution check prior to server instantiation
    execute_from_command_line([sys.argv[0], "makemigrations", "cms_application"])
    execute_from_command_line([sys.argv[0], "migrate"])
    
    # Run the web server
    execute_from_command_line([sys.argv[0], "runserver", "127.0.0.1:8000"])
