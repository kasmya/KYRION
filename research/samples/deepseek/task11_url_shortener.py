"""
URL Shortener Service with Flask and Redis backend.

Features:
- Generate short codes with base62 encoding
- Store URL mappings in Redis with TTL
- Redirect to original URLs
- Click tracking and analytics
- REST API for create/delete operations
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import string
import hashlib
import validators

from flask import Flask, request, redirect, jsonify, render_template, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from redis.exceptions import RedisError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('url_shortener.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Redis configuration
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

class URLShortener:
    """URL shortening service with Redis storage."""
    
    BASE62 = string.digits + string.ascii_lowercase + string.ascii_uppercase
    DEFAULT_TTL = 60 * 60 * 24 * 30  # 30 days
    SHORT_CODE_LENGTH = 7
    
    def __init__(self, redis_url: str = REDIS_URL):
        """
        Initialize URL shortener with Redis connection.
        
        Args:
            redis_url: Redis connection URL
        """
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("Connected to Redis")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise
    
    def _encode_base62(self, num: int) -> str:
        """
        Encode integer to base62 string.
        
        Args:
            num: Integer to encode
            
        Returns:
            Base62 encoded string
        """
        if num == 0:
            return self.BASE62[0]
        
        arr = []
        base = len(self.BASE62)
        
        while num:
            num, rem = divmod(num, base)
            arr.append(self.BASE62[rem])
        
        arr.reverse()
        return ''.join(arr)
    
    def _decode_base62(self, string: str) -> int:
        """
        Decode base62 string to integer.
        
        Args:
            string: Base62 encoded string
            
        Returns:
            Decoded integer
        """
        base = len(self.BASE62)
        strlen = len(string)
        num = 0
        
        for i, char in enumerate(string):
            power = strlen - (i + 1)
            num += self.BASE62.index(char) * (base ** power)
        
        return num
    
    def _generate_short_code(self, url: str) -> str:
        """
        Generate unique short code for URL.
        
        Args:
            url: Original URL
            
        Returns:
            Short code string
        """
        # Use MD5 hash for uniqueness
        hash_bytes = hashlib.md5(url.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
        
        # Add timestamp to ensure uniqueness
        timestamp = int(datetime.now().timestamp() * 1000)
        combined = hash_int ^ timestamp
        
        # Encode to base62
        short_code = self._encode_base62(combined)
        
        # Ensure minimum length
        while len(short_code) < self.SHORT_CODE_LENGTH:
            short_code += self._encode_base62(hash_int % 62)
            hash_int //= 62
        
        return short_code[:self.SHORT_CODE_LENGTH]
    
    def create_short_url(
        self,
        original_url: str,
        custom_code: Optional[str] = None,
        ttl: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a shortened URL.
        
        Args:
            original_url: Original long URL
            custom_code: Custom short code (optional)
            ttl: Time-to-live in seconds
            user_id: User identifier for tracking
            
        Returns:
            Dictionary with short URL information
        """
        # Validate URL
        if not original_url:
            raise ValueError("URL is required")
        
        if not original_url.startswith(('http://', 'https://')):
            original_url = 'https://' + original_url
        
        if not validators.url(original_url):
            raise ValueError("Invalid URL format")
        
        # Check if URL already shortened
        existing_code = self.redis.get(f"url_reverse:{original_url}")
        if existing_code:
            logger.info(f"URL already shortened: {existing_code}")
            return self.get_url_info(existing_code)
        
        # Generate or use custom code
        if custom_code:
            if self.redis.exists(f"url:{custom_code}"):
                raise ValueError(f"Custom code '{custom_code}' already exists")
            short_code = custom_code
        else:
            # Generate unique code
            for _ in range(5):  # Retry up to 5 times
                short_code = self._generate_short_code(original_url)
                if not self.redis.exists(f"url:{short_code}"):
                    break
            else:
                raise ValueError("Failed to generate unique short code")
        
        # Set TTL
        ttl = ttl or self.DEFAULT_TTL
        
        # Store URL mapping
        timestamp = datetime.now().isoformat()
        
        url_data = {
            'original_url': original_url,
            'short_code': short_code,
            'created_at': timestamp,
            'clicks': 0,
            'user_id': user_id or 'anonymous',
            'ttl': ttl
        }
        
        # Store mappings
        self.redis.hset(f"url:{short_code}", mapping=url_data)
        self.redis.expire(f"url:{short_code}", ttl)
        
        # Reverse mapping for duplicate checking
        self.redis.setex(f"url_reverse:{original_url}", ttl, short_code)
        
        # Add to user's URL list
        if user_id:
            self.redis.sadd(f"user_urls:{user_id}", short_code)
        
        # Track creation stats
        self.redis.hincrby("stats:global", "total_urls", 1)
        
        logger.info(f"Short URL created: {short_code} -> {original_url}")
        
        return self.get_url_info(short_code)
    
    def get_original_url(self, short_code: str) -> Optional[str]:
        """
        Retrieve original URL from short code.
        
        Args:
            short_code: Short code to look up
            
        Returns:
            Original URL or None if not found
        """
        original_url = self.redis.hget(f"url:{short_code}", "original_url")
        
        if original_url:
            # Increment click count asynchronously
            self._record_click(short_code)
        
        return original_url
    
    def _record_click(self, short_code: str) -> None:
        """
        Record click event for analytics.
        
        Args:
            short_code: Short code that was clicked
        """
        timestamp = datetime.now().isoformat()
        click_data = {
            'timestamp': timestamp,
            'ip': '0.0.0.0',  # Would get from request context
            'user_agent': 'Unknown'
        }
        
        # Increment total clicks
        self.redis.hincrby(f"url:{short_code}", "clicks", 1)
        
        # Store click event
        self.redis.lpush(f"clicks:{short_code}", str(click_data))
        self.redis.ltrim(f"clicks:{short_code}", 0, 999)  # Keep last 1000 clicks
        
        # Update global stats
        self.redis.hincrby("stats:global", "total_clicks", 1)
        
        # Track daily clicks
        date_key = datetime.now().strftime('%Y-%m-%d')
        self.redis.hincrby(f"stats:daily:{date_key}", "clicks", 1)
    
    def get_url_info(self, short_code: str) -> Dict[str, Any]:
        """
        Get information about a short URL.
        
        Args:
            short_code: Short code to look up
            
        Returns:
            Dictionary with URL information
        """
        url_data = self.redis.hgetall(f"url:{short_code}")
        
        if not url_data:
            raise ValueError(f"Short URL not found: {short_code}")
        
        # Get remaining TTL
        ttl = self.redis.ttl(f"url:{short_code}")
        
        return {
            'short_code': short_code,
            'short_url': f"{request.host_url}{short_code}" if request else short_code,
            'original_url': url_data.get('original_url'),
            'created_at': url_data.get('created_at'),
            'clicks': int(url_data.get('clicks', 0)),
            'user_id': url_data.get('user_id'),
            'expires_in_seconds': ttl if ttl > 0 else None
        }
    
    def delete_short_url(self, short_code: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a short URL.
        
        Args:
            short_code: Short code to delete
            user_id: User identifier for authorization
            
        Returns:
            True if deleted successfully
        """
        url_data = self.redis.hgetall(f"url:{short_code}")
        
        if not url_data:
            raise ValueError(f"Short URL not found: {short_code}")
        
        # Check ownership if user_id provided
        if user_id and url_data.get('user_id') != user_id:
            raise PermissionError("You don't have permission to delete this URL")
        
        # Get original URL for reverse mapping cleanup
        original_url = url_data.get('original_url')
        
        # Delete mappings
        self.redis.delete(f"url:{short_code}")
        self.redis.delete(f"url_reverse:{original_url}")
        self.redis.delete(f"clicks:{short_code}")
        
        # Remove from user's list
        if url_data.get('user_id'):
            self.redis.srem(f"user_urls:{url_data['user_id']}", short_code)
        
        # Update stats
        self.redis.hincrby("stats:global", "total_urls", -1)
        
        logger.info(f"Short URL deleted: {short_code}")
        
        return True
    
    def get_url_stats(self, short_code: str) -> Dict[str, Any]:
        """
        Get click statistics for a short URL.
        
        Args:
            short_code: Short code
            
        Returns:
            Dictionary with click statistics
        """
        url_data = self.redis.hgetall(f"url:{short_code}")
        
        if not url_data:
            raise ValueError(f"Short URL not found: {short_code}")
        
        # Get recent clicks
        clicks = self.redis.lrange(f"clicks:{short_code}", 0, 9)
        recent_clicks = [eval(click) for click in clicks]
        
        return {
            'short_code': short_code,
            'total_clicks': int(url_data.get('clicks', 0)),
            'recent_clicks': recent_clicks,
            'created_at': url_data.get('created_at')
        }
    
    def get_user_urls(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all URLs created by a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of URL information dictionaries
        """
        short_codes = self.redis.smembers(f"user_urls:{user_id}")
        
        urls = []
        for code in short_codes:
            try:
                url_info = self.get_url_info(code)
                urls.append(url_info)
            except ValueError:
                continue
        
        return urls
    
    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global URL shortener statistics.
        
        Returns:
            Dictionary with global statistics
        """
        stats = self.redis.hgetall("stats:global")
        
        return {
            'total_urls': int(stats.get('total_urls', 0)),
            'total_clicks': int(stats.get('total_clicks', 0))
        }

# Initialize URL shortener
try:
    shortener = URLShortener()
except RedisError:
    logger.error("Failed to initialize URL shortener. Using stub.")
    shortener = None

@app.route('/')
def index():
    """Home page with URL shortening form."""
    return render_template('shortener.html')

@app.route('/shorten', methods=['POST'])
@limiter.limit("10 per minute")
def shorten_url():
    """
    API endpoint to create short URL.
    
    Accepts JSON with:
    - url: Original URL (required)
    - custom_code: Custom short code (optional)
    - ttl: Time-to-live in seconds (optional)
    """
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        result = shortener.create_short_url(
            original_url=data['url'],
            custom_code=data.get('custom_code'),
            ttl=data.get('ttl'),
            user_id=data.get('user_id', request.remote_addr)
        )
        
        return jsonify(result), 201
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating short URL: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/<short_code>')
def redirect_to_url(short_code: str):
    """
    Redirect short code to original URL.
    Tracks click event.
    """
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        original_url = shortener.get_original_url(short_code)
        
        if original_url:
            return redirect(original_url, code=302)
        else:
            abort(404)
            
    except Exception as e:
        logger.error(f"Error redirecting: {str(e)}", exc_info=True)
        abort(500)

@app.route('/api/info/<short_code>')
def get_url_info(short_code: str):
    """Get information about a short URL."""
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        info = shortener.get_url_info(short_code)
        return jsonify(info)
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error getting URL info: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/stats/<short_code>')
def get_url_stats(short_code: str):
    """Get click statistics for a short URL."""
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        stats = shortener.get_url_stats(short_code)
        return jsonify(stats)
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/delete/<short_code>', methods=['DELETE'])
def delete_url(short_code: str):
    """Delete a short URL."""
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        data = request.get_json() or {}
        user_id = data.get('user_id', request.remote_addr)
        
        shortener.delete_short_url(short_code, user_id)
        return jsonify({'message': 'URL deleted successfully'})
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f"Error deleting URL: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/global-stats')
def get_global_stats():
    """Get global statistics."""
    try:
        if not shortener:
            return jsonify({'error': 'Service unavailable'}), 503
        
        stats = shortener.get_global_stats()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting global stats: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404

# HTML Templates
HTML_TEMPLATES = {
    'shortener.html': '''
<!DOCTYPE html>
<html>
<head>
    <title>URL Shortener</title>
    <style>
        body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
        .form { background: #f5f5f5; padding: 20px; border-radius: 5px; }
        input[type="url"] { width: 70%; padding: 10px; margin-right: 10px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        .result { margin-top: 20px; padding: 10px; background: #d4edda; border-radius: 5px; display: none; }
    </style>
</head>
<body>
    <h1>URL Shortener</h1>
    <div class="form">
        <input type="url" id="urlInput" placeholder="Enter your long URL here..." required>
        <button onclick="shortenUrl()">Shorten</button>
    </div>
    <div id="result" class="result"></div>
    <script>
        async function shortenUrl() {
            const url = document.getElementById('urlInput').value;
            const response = await fetch('/shorten', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            });
            const data = await response.json();
            const resultDiv = document.getElementById('result');
            resultDiv.style.display = 'block';
            if (data.short_url) {
                resultDiv.innerHTML = `Short URL: <a href="${data.short_url}">${data.short_url}</a>`;
            } else {
                resultDiv.innerHTML = `Error: ${data.error}`;
            }
        }
    </script>
</body>
</html>
''',
    '404.html': '<h1>404 - URL Not Found</h1><p>The requested short URL does not exist.</p>'
}

def create_templates():
    """Create template files."""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    for filename, content in HTML_TEMPLATES.items():
        with open(os.path.join(templates_dir, filename), 'w') as f:
            f.write(content)

if __name__ == '__main__':
    create_templates()
    app.run(debug=True, host='0.0.0.0', port=5001)
