import subprocess
import re
import os
import uuid
import shutil
import instaloader
from flask import Flask, request, render_template, send_from_directory, redirect, url_for, flash, abort

# --- Configuration ---
app = Flask(__name__)
# Replace with a strong secret key in production
app.secret_key = os.urandom(24)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * \
    1024  # Optional: Limit request size (e.g., 5MB)

# --- Helper Functions ---


def sanitize_filename(filename):
    """Sanitize the filename to make it safe for use in paths."""
    # Replace newline characters with an underscore and remove special characters
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    # Replace newlines specifically with underscores
    sanitized = sanitized.replace('\n', '_')
    return sanitized


def extract_shortcode(url):
    """Extracts the shortcode from an Instagram URL."""
    match = re.search(r"(?:reel|p)/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def find_media_file(directory, extensions=('.mp4', '.jpg', '.png', '.jpeg')):
    """Finds the first media file with given extensions in the directory."""
    for filename in os.listdir(directory):
        if filename.lower().endswith(extensions):
            return os.path.join(directory, filename)
    return None


def extract_audio_ffmpeg(video_path, output_path):
    """Extracts audio using ffmpeg without re-encoding."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if shutil.which("ffmpeg") is None:
        app.logger.error("ffmpeg not found in PATH.")
        return False, "Server configuration error: ffmpeg not found."

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

    app.logger.info(f"Running ffmpeg command: {' '.join(command)}")
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=120)
        app.logger.info(f"FFmpeg stdout: {result.stdout}")
        app.logger.info(f"FFmpeg stderr: {result.stderr}")
        return True, f"Audio successfully extracted to: {os.path.basename(output_path)}"
    except subprocess.TimeoutExpired:
        app.logger.error("FFmpeg process timed out.")
        return False, "Error: Audio extraction took too long."
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Error during ffmpeg execution: {e}")
        return False, "Error during audio extraction."


# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main page with the URL input form."""
    return render_template('index.html')


@app.route('/download', methods=['POST'])
def download_audio():
    """Handles the form submission, downloads video, extracts audio."""
    reel_url = request.form.get('reel_url')

    if not reel_url:
        flash('Please provide an Instagram Reel URL.', 'error')
        return redirect(url_for('index'))

    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        flash('Invalid Instagram Reel URL format.', 'error')
        return redirect(url_for('index'))

    # Create a unique temporary directory for this request
    request_id = str(uuid.uuid4())
    temp_download_dir = os.path.join(
        app.config['DOWNLOAD_FOLDER'], f"temp_{request_id}")
    os.makedirs(temp_download_dir, exist_ok=True)

    # Instaloader setup
    L = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=temp_download_dir,
        filename_pattern="{shortcode}"
    )

    video_file_path = None
    final_audio_filename = None

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            flash('The provided link does not point to a video Reel.', 'error')
            shutil.rmtree(temp_download_dir)
            return redirect(url_for('index'))

        # Download the post
        L.download_post(post, target="")

        video_file_path = find_media_file(
            temp_download_dir, extensions=('.mp4',))
        if not video_file_path:
            flash('Failed to download the video file from Instagram.', 'error')
            shutil.rmtree(temp_download_dir)
            return redirect(url_for('index'))

        reel_name = post.title  # Get the reel name (title)
        print(reel_name)
        sanitized_reel_name = sanitize_filename(reel_name)  # Sanitize the title
        final_audio_filename = f"{sanitized_reel_name}_{request_id}.mp3"

        output_audio_path = os.path.join(
            app.config['DOWNLOAD_FOLDER'], final_audio_filename)

        success, message = extract_audio_ffmpeg(
            video_file_path, output_audio_path)

        if not success:
            flash(message, 'error')
            return redirect(url_for('index'))

        flash(f'Audio ready: {final_audio_filename}', 'success')
        return redirect(url_for('serve_file', filename=final_audio_filename))

    except instaloader.exceptions.InstaloaderException as e:
        flash(f"Error interacting with Instagram: {e}", 'error')
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {e}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('index'))
    finally:
        # Cleanup temp directory
        if os.path.exists(temp_download_dir):
            try:
                shutil.rmtree(temp_download_dir)
            except OSError as e:
                app.logger.warning(f"Could not remove temp directory: {e}")


@app.route('/serve/<filename>')
def serve_file(filename):
    """Serves the extracted audio file for download."""
    try:
        if '..' in filename or filename.startswith('/'):
            abort(404)

        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if not os.path.isfile(file_path):
            abort(404)

        return send_from_directory(
            app.config['DOWNLOAD_FOLDER'],
            filename,
            as_attachment=True,
            mimetype='audio/mp4'
        )
    except FileNotFoundError:
        app.logger.error(f"File not found: {filename}")
        abort(404)
    except Exception as e:
        app.logger.error(f"Error serving file: {e}", exc_info=True)
        abort(500)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
