"""
Django Blog CMS with user authentication, post management, and comments.

Project structure (blog_cms/):
- manage.py
- blog_cms/settings.py
- blog_cms/urls.py
- blog_cms/wsgi.py
- blog/models.py
- blog/views.py
- blog/urls.py
- blog/forms.py
- blog/admin.py
- blog/feeds.py
"""

# ============================================
# File: blog_cms/settings.py
# ============================================
"""
Django settings for blog_cms project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-change-this-in-production-1234567890'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.syndication',
    
    # Third party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'taggit',
    'django.contrib.postgres',  # For PostgreSQL full-text search
    
    # Local
    'blog',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'blog_cms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'blog_cms.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# ============================================
# File: blog/models.py
# ============================================
"""
Blog models for posts, categories, tags, and comments.
"""

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from taggit.managers import TaggableManager


class Category(models.Model):
    """Blog post categories."""
    
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('blog:category_detail', args=[self.slug])
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Post(models.Model):
    """Blog post model."""
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
    )
    
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique_for_date='published_at')
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='blog_posts'
    )
    body = models.TextField()
    excerpt = models.TextField(blank=True)
    featured_image = models.ImageField(
        upload_to='blog/images/%Y/%m/', blank=True
    )
    
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name='posts'
    )
    tags = TaggableManager()
    
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='draft'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(default=timezone.now)
    
    # SEO fields
    meta_title = models.CharField(max_length=250, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    
    # Statistics
    views = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['status', '-published_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('blog:post_detail', args=[
            self.published_at.year,
            self.published_at.month,
            self.published_at.day,
            self.slug
        ])
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.excerpt:
            self.excerpt = self.body[:200]
        super().save(*args, **kwargs)


class Comment(models.Model):
    """Blog post comments."""
    
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name='comments'
    )
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='comments'
    )
    body = models.TextField()
    
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='replies'
    )
    
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f'Comment by {self.author.username} on {self.post.title}'
    
    def approve(self):
        """Approve the comment."""
        self.is_approved = True
        self.save()


class UserProfile(models.Model):
    """Extended user profile."""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True)
    website = models.URLField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    
    def __str__(self):
        return f'Profile of {self.user.username}'


# ============================================
# File: blog/views.py
# ============================================
"""
Blog views for post listing, detail, comments, and search.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils import timezone

from .models import Post, Category, Comment, UserProfile
from .forms import PostForm, CommentForm, SearchForm


class PostListView(ListView):
    """List published blog posts with pagination."""
    
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = Post.objects.filter(
            status='published',
            published_at__lte=timezone.now()
        ).select_related('author', 'category').prefetch_related('tags')
        
        # Category filter
        category_slug = self.kwargs.get('category_slug')
        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            queryset = queryset.filter(category=category)
        
        # Tag filter
        tag_slug = self.kwargs.get('tag_slug')
        if tag_slug:
            queryset = queryset.filter(tags__slug=tag_slug)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.annotate(
            post_count=Count('posts')
        )
        return context


class PostDetailView(DetailView):
    """Display single blog post."""
    
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'
    
    def get_queryset(self):
        return Post.objects.filter(
            status='published'
        ).select_related('author', 'category').prefetch_related('tags', 'comments')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.get_object()
        
        # Increment view count
        post.views += 1
        post.save(update_fields=['views'])
        
        # Comments
        comments = post.comments.filter(
            is_approved=True, parent=None
        ).select_related('author')
        
        context['comments'] = comments
        context['comment_form'] = CommentForm()
        context['related_posts'] = Post.objects.filter(
            tags__in=post.tags.all()
        ).exclude(id=post.id).distinct()[:5]
        
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    """Create new blog post."""
    
    model = Post
    form_class = PostForm
    template_name = 'blog/post_form.html'
    
    def form_valid(self, form):
        form.instance.author = self.request.user
        if form.cleaned_data['status'] == 'published':
            form.instance.published_at = timezone.now()
        return super().form_valid(form)


class PostUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update existing blog post."""
    
    model = Post
    form_class = PostForm
    template_name = 'blog/post_form.html'
    
    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author or self.request.user.is_staff
    
    def form_valid(self, form):
        if form.cleaned_data['status'] == 'published' and not self.object.published_at:
            form.instance.published_at = timezone.now()
        return super().form_valid(form)


class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete blog post."""
    
    model = Post
    template_name = 'blog/post_confirm_delete.html'
    success_url = reverse_lazy('blog:post_list')
    
    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author or self.request.user.is_staff


@login_required
@require_POST
def add_comment(request, pk):
    """Add comment to post."""
    post = get_object_or_404(Post, id=pk, status='published')
    form = CommentForm(request.POST)
    
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        
        # Check if replying to another comment
        parent_id = request.POST.get('parent_id')
        if parent_id:
            comment.parent = get_object_or_404(Comment, id=parent_id)
        
        comment.save()
        messages.success(request, 'Comment added successfully!')
    else:
        messages.error(request, 'Error adding comment. Please try again.')
    
    return redirect(post.get_absolute_url())


@login_required
def approve_comment(request, pk):
    """Approve comment (author only)."""
    comment = get_object_or_404(Comment, id=pk)
    
    if request.user == comment.post.author or request.user.is_staff:
        comment.approve()
        messages.success(request, 'Comment approved!')
    
    return redirect(comment.post.get_absolute_url())


class SearchView(ListView):
    """Search blog posts."""
    
    model = Post
    template_name = 'blog/search_results.html'
    context_object_name = 'results'
    paginate_by = 10
    
    def get_queryset(self):
        query = self.request.GET.get('q', '')
        
        if query:
            return Post.objects.filter(
                Q(title__icontains=query) |
                Q(body__icontains=query) |
                Q(tags__name__icontains=query)
            ).filter(status='published').distinct()
        
        return Post.objects.none()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


# ============================================
# File: blog/urls.py
# ============================================
"""
URL configuration for blog app.
"""

from django.urls import path
from .. import views
from .feeds import LatestPostsFeed

app_name = 'blog'

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('search/', views.SearchView.as_view(), name='search'),
    path('feed/', LatestPostsFeed(), name='post_feed'),
    path('post/new/', views.PostCreateView.as_view(), name='post_create'),
    path('post/<int:pk>/edit/', views.PostUpdateView.as_view(), name='post_update'),
    path('post/<int:pk>/delete/', views.PostDeleteView.as_view(), name='post_delete'),
    path('post/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('comment/<int:pk>/approve/', views.approve_comment, name='approve_comment'),
    path(
        '<int:year>/<int:month>/<int:day>/<slug:slug>/',
        views.PostDetailView.as_view(),
        name='post_detail'
    ),
    path('category/<slug:category_slug>/', views.PostListView.as_view(), name='category_detail'),
    path('tag/<slug:tag_slug>/', views.PostListView.as_view(), name='tag_detail'),
]


# ============================================
# File: blog/forms.py
# ============================================
"""
Forms for blog posts and comments.
"""

from django import forms
from .models import Post, Comment


class PostForm(forms.ModelForm):
    """Form for creating/editing blog posts."""
    
    class Meta:
        model = Post
        fields = [
            'title', 'body', 'excerpt', 'category', 'tags',
            'status', 'featured_image', 'meta_title', 'meta_description'
        ]
        widgets = {
            'body': forms.Textarea(attrs={'class': 'editor'}),
            'excerpt': forms.Textarea(attrs={'rows': 3}),
        }


class CommentForm(forms.ModelForm):
    """Form for adding comments."""
    
    class Meta:
        model = Comment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write your comment...'})
        }


class SearchForm(forms.Form):
    """Search form."""
    
    q = forms.CharField(
        label='Search',
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Search posts...'})
    )


# ============================================
# File: blog/feeds.py
# ============================================
"""
RSS feed for blog posts.
"""

from django.contrib.syndication.views import Feed
from django.template.defaultfilters import truncatewords
from django.urls import reverse_lazy
from .models import Post


class LatestPostsFeed(Feed):
    """RSS feed for latest published posts."""
    
    title = "My Blog"
    link = reverse_lazy('blog:post_list')
    description = "Latest posts from my blog"
    
    def items(self):
        return Post.objects.filter(status='published')[:20]
    
    def item_title(self, item):
        return item.title
    
    def item_description(self, item):
        return truncatewords(item.body, 30)
    
    def item_pubdate(self, item):
        return item.published_at


# ============================================
# File: blog_cms/urls.py
# ============================================
"""
Main URL configuration for blog_cms project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('blog.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# ============================================
# File: blog/admin.py
# ============================================
"""
Admin configuration for blog models.
"""

from django.contrib import admin
from .models import Post, Category, Comment, UserProfile


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Admin interface for posts."""
    
    list_display = ['title', 'author', 'category', 'status', 'published_at', 'views']
    list_filter = ['status', 'created_at', 'published_at', 'category']
    search_fields = ['title', 'body']
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ['author']
    date_hierarchy = 'published_at'
    ordering = ['status', '-published_at']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'post', 'created_at', 'is_approved']
    list_filter = ['is_approved', 'created_at']
    actions = ['approve_comments']
    
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'website']


# ============================================
# File: manage.py
# ============================================
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blog_cms.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
