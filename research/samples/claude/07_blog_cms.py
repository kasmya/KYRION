"""
### Task 7: Blog CMS (Django)

A single-file, runnable Django blog CMS demonstrating user authentication,
post CRUD with authors/tags/categories, moderated comments, search, and an
RSS feed. Structured as one file for portability; in a real project this
would be split into apps/models.py, views.py, urls.py, etc.

Requirements:
    pip install django

Run:
    python 07_blog_cms.py migrate
    python 07_blog_cms.py createsuperuser
    python 07_blog_cms.py runserver
"""

from __future__ import annotations

import logging
import os
import sys

import django
from django.conf import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("blog_cms")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="change-this-secret-key-in-production",  # nosec
        ALLOWED_HOSTS=["*"],
        ROOT_URLCONF=__name__,
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
            "django.contrib.sites",
            "blog_cms",
        ],
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": os.path.join(BASE_DIR, "blog_cms.db"),
            }
        },
        SITE_ID=1,
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.debug",
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                    ],
                },
            },
        ],
        STATIC_URL="/static/",
    )
    django.setup()


from django.contrib import admin  # noqa: E402
from django.contrib.auth.decorators import login_required  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.contrib.syndication.views import Feed  # noqa: E402
from django.db import models  # noqa: E402
from django.http import HttpRequest, HttpResponse, JsonResponse  # noqa: E402
from django.shortcuts import get_object_or_404  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.views.decorators.csrf import csrf_exempt  # noqa: E402
from django.views.decorators.http import require_http_methods  # noqa: E402


class Category(models.Model):
    """A blog post category."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        app_label = "blog_cms"

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    """A free-form tag attachable to posts."""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        app_label = "blog_cms"

    def __str__(self) -> str:
        return self.name


class Post(models.Model):
    """A blog post authored by a user, optionally categorized and tagged."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        app_label = "blog_cms"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Comment(models.Model):
    """A comment on a post, subject to moderation before being publicly visible."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author_name = models.CharField(max_length=100)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    class Meta:
        app_label = "blog_cms"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment by {self.author_name} on {self.post.title}"


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "is_published", "created_at")
    search_fields = ("title", "content")
    list_filter = ("category", "is_published")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author_name", "is_approved", "created_at")
    list_filter = ("is_approved",)
    actions = ["approve_comments"]

    def approve_comments(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} comment(s) approved.")


admin.site.register(Category)
admin.site.register(Tag)


def post_list_view(request: HttpRequest) -> JsonResponse:
    """Lists published posts, optionally filtered by a search query or tag."""
    query = request.GET.get("q")
    tag = request.GET.get("tag")

    posts = Post.objects.filter(is_published=True)
    if query:
        posts = posts.filter(models.Q(title__icontains=query) | models.Q(content__icontains=query))
    if tag:
        posts = posts.filter(tags__name__iexact=tag)

    data = [
        {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "author": p.author.username,
            "category": p.category.name if p.category else None,
            "tags": list(p.tags.values_list("name", flat=True)),
            "created_at": p.created_at.isoformat(),
        }
        for p in posts.distinct()
    ]
    return JsonResponse({"count": len(data), "results": data})


def post_detail_view(request: HttpRequest, slug: str) -> JsonResponse:
    """Returns a single post with its approved comments."""
    post = get_object_or_404(Post, slug=slug, is_published=True)
    comments = post.comments.filter(is_approved=True)
    return JsonResponse(
        {
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "author": post.author.username,
            "category": post.category.name if post.category else None,
            "tags": list(post.tags.values_list("name", flat=True)),
            "comments": [
                {"author_name": c.author_name, "body": c.body, "created_at": c.created_at.isoformat()}
                for c in comments
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def post_create_view(request: HttpRequest) -> JsonResponse:
    """Creates a new post, authored by the currently authenticated user."""
    import json as json_lib

    try:
        payload = json_lib.loads(request.body)
        title = payload["title"].strip()
        content = payload["content"]
        slug = payload.get("slug") or title.lower().replace(" ", "-")
        category_name = payload.get("category")
        tag_names = payload.get("tags", [])
    except (KeyError, ValueError, json_lib.JSONDecodeError) as exc:
        return JsonResponse({"error": f"invalid payload: {exc}"}, status=400)

    if Post.objects.filter(slug=slug).exists():
        return JsonResponse({"error": "a post with this slug already exists"}, status=409)

    category = None
    if category_name:
        category, _ = Category.objects.get_or_create(name=category_name)

    post = Post.objects.create(
        title=title, slug=slug, content=content, author=request.user, category=category
    )
    for tag_name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=tag_name)
        post.tags.add(tag)

    logger.info("User '%s' created post '%s'", request.user.username, post.title)
    return JsonResponse({"id": post.id, "slug": post.slug}, status=201)


@require_http_methods(["POST"])
@csrf_exempt
def comment_create_view(request: HttpRequest, slug: str) -> JsonResponse:
    """Submits a new comment for moderation (not immediately visible)."""
    import json as json_lib

    post = get_object_or_404(Post, slug=slug, is_published=True)
    try:
        payload = json_lib.loads(request.body)
        author_name = payload["author_name"].strip()
        body = payload["body"].strip()
    except (KeyError, ValueError, json_lib.JSONDecodeError) as exc:
        return JsonResponse({"error": f"invalid payload: {exc}"}, status=400)

    if not author_name or not body:
        return JsonResponse({"error": "author_name and body are required"}, status=400)

    comment = Comment.objects.create(post=post, author_name=author_name, body=body, is_approved=False)
    logger.info("New comment submitted for moderation on post '%s'", post.title)
    return JsonResponse({"id": comment.id, "status": "pending moderation"}, status=201)


class LatestPostsFeed(Feed):
    """RSS feed of the most recently published posts."""

    title = "Blog CMS - Latest Posts"
    link = "/rss/"
    description = "Recent posts from the Blog CMS."

    def items(self):
        return Post.objects.filter(is_published=True).order_by("-created_at")[:20]

    def item_title(self, item: Post) -> str:
        return item.title

    def item_description(self, item: Post) -> str:
        return item.content[:300]

    def item_link(self, item: Post) -> str:
        return reverse("post_detail", args=[item.slug])


from django.urls import path  # noqa: E402

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/posts/", post_list_view, name="post_list"),
    path("api/posts/create/", post_create_view, name="post_create"),
    path("api/posts/<slug:slug>/", post_detail_view, name="post_detail"),
    path("api/posts/<slug:slug>/comments/", comment_create_view, name="comment_create"),
    path("rss/", LatestPostsFeed(), name="post_feed"),
]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
