import os
import re
import uuid
import shutil
import subprocess
import instaloader
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, abort

# --- Configuration ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * \
    1024 * 1024  # Optional: Limit upload size

# --- Helper Functions ---



def extract_shortcode(url):
    match = re.search(r"(?:reel|p)/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def sanitize_filename(filename):
    if not filename:
        return "Instagram_Reel"
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    return sanitized.replace('\n', '_').strip('_')


def find_media_file(directory, extensions=('.mp4', '.jpg', '.png', '.jpeg')):
    for filename in os.listdir(directory):
        if filename.lower().endswith(extensions):
            return os.path.join(directory, filename)
    return None


def extract_audio_ffmpeg(video_path, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if shutil.which("ffmpeg") is None:
        app.logger.error("ffmpeg not found.")
        return False, "Server error: ffmpeg not installed."

    command = [
        'ffmpeg',
        '-i', video_path,
        '-vn',
        '-acodec', 'libmp3lame',
        '-ab', '256k',
        '-ar', '44100',
        '-ac', '2',
        '-f', 'mp3',
        '-y',
        output_path
    ]

    try:
        result = subprocess.run(command, check=True,
                                capture_output=True, text=True, timeout=120)
        app.logger.info(f"FFmpeg output: {result.stdout}")
        return True, f"Audio extracted: {os.path.basename(output_path)}"
    except subprocess.TimeoutExpired:
        return False, "Error: Audio extraction timed out."
    except subprocess.CalledProcessError as e:
        app.logger.error(f"FFmpeg error: {e.stderr}")
        return False, "FFmpeg failed during audio extraction."

# --- Flask Routes ---


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/download', methods=['POST'])
def download_audio():
    reel_url = request.form.get('reel_url', '').strip()

    if not reel_url:
        flash('Please enter an Instagram Reel URL.', 'error')
        return redirect(url_for('index'))

    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        flash('Invalid Instagram Reel URL.', 'error')
        return redirect(url_for('index'))

    request_id = str(uuid.uuid4())
    temp_dir = os.path.join(
        app.config['DOWNLOAD_FOLDER'], f"temp_{request_id}")
    os.makedirs(temp_dir, exist_ok=True)

    L = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=temp_dir,
        filename_pattern="{shortcode}"
    )

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            flash('This is not a video Reel.', 'error')
            return redirect(url_for('index'))

        L.download_post(post, target="")

        video_path = find_media_file(temp_dir, extensions=('.mp4',))
        if not video_path:
            flash('Video download failed.', 'error')
            return redirect(url_for('index'))

        sanitized_title = sanitize_filename(post.caption)
        final_audio_filename = f"{sanitized_title}_{request_id}.mp3"
        output_audio_path = os.path.join(
            app.config['DOWNLOAD_FOLDER'], final_audio_filename)

        success, message = extract_audio_ffmpeg(video_path, output_audio_path)
        if not success:
            flash(message, 'error')
            return redirect(url_for('index'))

        flash(f'Audio ready: {final_audio_filename}', 'success')
        return redirect(url_for('serve_file', filename=final_audio_filename))

    except instaloader.exceptions.InstaloaderException as e:
        app.logger.error(f"Instaloader error: {e}")
        flash(f"Error with Instagram: {e}", 'error')
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}", exc_info=True)
        flash("Unexpected error occurred.", 'error')
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return redirect(url_for('index'))


@app.route('/serve/<filename>')
def serve_file(filename):
    if '..' in filename or filename.startswith('/'):
        abort(404)

    file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
    if not os.path.isfile(file_path):
        abort(404)

    return send_from_directory(
        app.config['DOWNLOAD_FOLDER'],
        filename,
        as_attachment=True,
        mimetype='audio/mpeg'  # Correct MIME type for MP3
    )


# --- Main Runner ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
