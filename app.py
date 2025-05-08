import os
import re
import uuid
import shutil
import subprocess
import instaloader
import json
import time
import random
import threading
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, abort
from datetime import datetime, timedelta

# --- Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
STATS_FILE = os.path.join(BASE_DIR, 'download_stats.json')
SESSION_FILE = os.path.join(BASE_DIR, 'instagram_session.json')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Rate limiting configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 5  # Increased initial delay
MAX_REQUESTS_PER_HOUR = 50
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
]

class RateLimiter:
    def __init__(self):
        self.requests = []
        self.lock = threading.Lock()

    def can_make_request(self):
        now = time.time()
        with self.lock:
            # Remove old requests
            self.requests = [req_time for req_time in self.requests 
                           if now - req_time < RATE_LIMIT_WINDOW]
            
            if len(self.requests) >= MAX_REQUESTS_PER_HOUR:
                return False
            
            self.requests.append(now)
            return True

    def get_wait_time(self):
        if not self.requests:
            return 0
        oldest_request = min(self.requests)
        return max(0, RATE_LIMIT_WINDOW - (time.time() - oldest_request))

rate_limiter = RateLimiter()

def get_instaloader():
    """Create and configure an Instaloader instance with session handling."""
    L = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        user_agent=random.choice(USER_AGENTS)
    )
    
    # Try to load existing session
    if os.path.exists(SESSION_FILE):
        try:
            L.load_session_from_file('instagram_session')
            app.logger.info("Loaded existing Instagram session")
        except Exception as e:
            app.logger.warning(f"Failed to load session: {e}")
    
    return L

def save_instaloader_session(L):
    """Save the current Instagram session."""
    try:
        L.save_session_to_file('instagram_session')
        app.logger.info("Saved Instagram session")
    except Exception as e:
        app.logger.warning(f"Failed to save session: {e}")

def init_stats():
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'w') as f:
            json.dump({'total_downloads': 0}, f)

def get_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'total_downloads': 0}

def update_stats():
    stats = get_stats()
    stats['total_downloads'] += 1
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)
    return stats['total_downloads']

# Initialize stats on startup
init_stats()

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Limit upload size

# --- Helper Functions ---
def cleanup_old_files():
    """Delete all files in the downloads folder."""
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            app.logger.error(f"Error deleting {file_path}: {e}")


def extract_shortcode(url):
    """Extracts the shortcode from an Instagram URL."""
    match = re.search(r"(?:reel|p)/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def generate_safe_filename(caption, max_length=100):
    """
    Generate a safe filename from caption only.
    Keeps letters, digits, underscores, hyphens; truncates to max_length.
    """
    if not caption:
        base = 'Instagram_Reel'
    else:
        base = re.sub(r'[^\w\s-]', '', caption)
        base = re.sub(r'[\s]+', '_', base).strip('_')
    truncated = base[:max_length]
    return f"{truncated}.mp3"


def find_media_file(directory, extensions=('.mp4', '.jpg', '.png', '.jpeg')):
    """Finds the first media file with given extensions in the directory."""
    for filename in os.listdir(directory):
        if filename.lower().endswith(extensions):
            return os.path.join(directory, filename)
    return None


def extract_audio_ffmpeg(video_path, output_path):
    """Extracts audio using ffmpeg to mp3 format."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if shutil.which('ffmpeg') is None:
        app.logger.error('ffmpeg not found')
        return False, 'Server error: ffmpeg not installed.'
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn', '-acodec', 'libmp3lame', '-ab', '256k', '-ar', '44100', '-ac', '2',
        '-f', 'mp3', '-y', output_path
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=120)
        app.logger.info(f"FFmpeg succeeded: {result.stdout}")
        return True, f"Audio ready: {os.path.basename(output_path)}"
    except subprocess.TimeoutExpired:
        return False, 'Error: Audio extraction timed out.'
    except subprocess.CalledProcessError as e:
        app.logger.error(f"FFmpeg error: {e.stderr}")
        return False, 'Error during audio extraction.'

def handle_instagram_error(error):
    """Handle Instagram API errors with user-friendly messages."""
    error_str = str(error).lower()
    
    if "rate limit" in error_str or "wait a few minutes" in error_str:
        wait_time = rate_limiter.get_wait_time()
        if wait_time > 0:
            return f"Instagram is temporarily limiting requests. Please try again in {int(wait_time/60)} minutes."
        return "Instagram is temporarily limiting requests. Please try again in a few minutes."
    elif "403" in error_str or "forbidden" in error_str:
        return "Access to this content is forbidden. The reel might be private or restricted."
    elif "401" in error_str or "unauthorized" in error_str:
        return "Authentication required. Please try again in a few minutes."
    elif "login required" in error_str:
        return "This reel is private or requires login to access."
    elif "not found" in error_str:
        return "The reel could not be found. Please check the URL."
    else:
        return f"Error accessing Instagram: {str(error)}"

def download_with_retry(L, post, max_retries=MAX_RETRIES):
    """Attempt to download with exponential backoff retry and rate limiting."""
    retry_delay = INITIAL_RETRY_DELAY
    
    for attempt in range(max_retries):
        if not rate_limiter.can_make_request():
            wait_time = rate_limiter.get_wait_time()
            raise instaloader.exceptions.InstaloaderException(
                f"Rate limit exceeded. Please wait {int(wait_time/60)} minutes."
            )
            
        try:
            L.download_post(post, target='')
            save_instaloader_session(L)  # Save successful session
            return True
        except instaloader.exceptions.InstaloaderException as e:
            if attempt == max_retries - 1:  # Last attempt
                raise e
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
            continue
    return False

# --- Flask Routes ---


@app.route('/')
def index():
    stats = get_stats()
    return render_template('index.html', total_downloads=stats['total_downloads'])


@app.route('/download', methods=['POST'])
def download_audio():
    # Clean up old files before downloading new one
    cleanup_old_files()
    
    reel_url = request.form.get('reel_url', '').strip()
    if not reel_url:
        flash('Please enter an Instagram Reel URL.', 'error')
        return redirect(url_for('index'))

    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        flash('Invalid Instagram Reel URL.', 'error')
        return redirect(url_for('index'))

    temp_id = str(uuid.uuid4())
    temp_dir = os.path.join(app.config['DOWNLOAD_FOLDER'], f"temp_{temp_id}")
    os.makedirs(temp_dir, exist_ok=True)

    L = get_instaloader()
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        if not post.is_video:
            flash('This is not a video Reel.', 'error')
            return redirect(url_for('index'))

        # Use retry mechanism for download
        if not download_with_retry(L, post):
            flash('Failed to download after multiple attempts. Please try again later.', 'error')
            return redirect(url_for('index'))

        video_path = find_media_file(temp_dir, extensions=('.mp4',))
        if not video_path:
            flash('Video download failed.', 'error')
            return redirect(url_for('index'))

        caption = post.caption or shortcode
        final_audio_filename = generate_safe_filename(caption)
        output_audio_path = os.path.join(
            app.config['DOWNLOAD_FOLDER'], final_audio_filename)

        success, msg = extract_audio_ffmpeg(video_path, output_audio_path)
        if not success:
            flash(msg, 'error')
            return redirect(url_for('index'))

        # Update download count
        total_downloads = update_stats()

        # Flash a link to download and reset page
        dl_link = url_for('serve_file', filename=final_audio_filename)
        flash(
            f'Audio ready: <a href="{dl_link}" target="_blank">Download here</a>', 'success')
        return redirect(url_for('index'))

    except instaloader.exceptions.InstaloaderException as e:
        app.logger.error(f"Instaloader error: {e}")
        error_message = handle_instagram_error(e)
        flash(error_message, 'error')
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}", exc_info=True)
        flash('Unexpected error occurred.', 'error')
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return redirect(url_for('index'))


@app.route('/serve/<filename>')
def serve_file(filename):
    if '..' in filename or filename.startswith('/'):
        abort(404)
    path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
    if not os.path.isfile(path):
        abort(404)
    
    try:
        return send_from_directory(
            app.config['DOWNLOAD_FOLDER'], filename,
            as_attachment=True, mimetype='audio/mpeg'
        )
    finally:
        # Clean up the file after serving
        try:
            os.unlink(path)
        except Exception as e:
            app.logger.error(f"Error deleting {path}: {e}")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
