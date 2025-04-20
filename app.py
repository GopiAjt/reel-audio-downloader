import instaloader
import os
import subprocess
import sys
import re
import shutil
import uuid  # To create unique temporary directories
from flask import (
    Flask, request, render_template, send_from_directory,
    redirect, url_for, flash, abort
)

# --- Configuration ---
app = Flask(__name__)
# Replace with a strong secret key in production
app.secret_key = os.urandom(24)

# Use absolute paths for reliability
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
# Ensure download folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * \
    1024  # Optional: Limit request size (e.g., 5MB)

# --- Helper Functions (Adapted from previous script) ---


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
    # Ensure output directory exists (redundant if DOWNLOAD_FOLDER check works, but safe)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Check if ffmpeg exists
    if shutil.which("ffmpeg") is None:
        app.logger.error("ffmpeg not found in PATH.")
        return False, "Server configuration error: ffmpeg not found."

    command = [
        'ffmpeg',
        '-i', video_path,
        '-vn',
        '-acodec', 'libmp3lame',
        '-ab', '256k',  # Bitrate for audio
        '-ar', '44100',  # Sample rate
        '-ac', '2',  # Stereo
        '-f', 'mp3',  # Output format
        '-y',  # Overwrite output file if it exists
        output_path
    ]

    app.logger.info(f"Running ffmpeg command: {' '.join(command)}")
    try:
        # Using stderr=subprocess.PIPE to capture ffmpeg's progress/info output
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=120)  # Added timeout
        app.logger.info(f"FFmpeg stdout: {result.stdout}")
        app.logger.info(f"FFmpeg stderr: {result.stderr}")
        return True, f"Audio successfully extracted to: {os.path.basename(output_path)}"
    except subprocess.TimeoutExpired:
        app.logger.error("FFmpeg process timed out.")
        return False, "Error: Audio extraction took too long."
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Error during ffmpeg execution: {e}")
        app.logger.error(f"FFmpeg stderr: {e.stderr}")
        # Try to provide a slightly more helpful error
        error_message = "Error during audio extraction."
        if "No such file or directory" in e.stderr:
            error_message = "Error: Input video file not found for ffmpeg."
        elif "Permission denied" in e.stderr:
            error_message = "Error: Permission denied during ffmpeg operation."
        return False, error_message
    except FileNotFoundError:
        app.logger.error("ffmpeg command not found during subprocess run.")
        return False, "Server configuration error: ffmpeg command not found."
    except Exception as e:
        app.logger.error(
            f"An unexpected error occurred during ffmpeg execution: {e}")
        return False, "An unexpected error occurred during audio extraction."


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

    # --- Instaloader Setup (No Login for simplicity in web app) ---
    L = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=temp_download_dir,  # Download directly into unique temp dir
        # Simplify filename if possible (might still add date)
        filename_pattern="{shortcode}"
    )
    # L.context.raise_all_errors = True # Be more explicit about errors

    video_file_path = None
    final_audio_filename = None

    try:
        app.logger.info(
            f"Attempting to download Reel: {shortcode} for request {request_id}")
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            flash('The provided link does not point to a video Reel.', 'error')
            shutil.rmtree(temp_download_dir)  # Clean up temp dir
            return redirect(url_for('index'))

        # Download the post - Instaloader will place it in temp_download_dir
        # profile=None avoids profile-named subdirs
        L.download_post(post, target="")
        app.logger.info(
            f"Post download attempted for {shortcode} into {temp_download_dir}")

        # Find the downloaded video file (.mp4) in the temp directory
        video_file_path = find_media_file(
            temp_download_dir, extensions=('.mp4',))
        if not video_file_path:
            # Sometimes instaloader fails silently or names differently, check logs
            app.logger.error(
                f"Could not find downloaded .mp4 video file in {temp_download_dir}")
            flash('Failed to download the video file from Instagram.', 'error')
            shutil.rmtree(temp_download_dir)
            return redirect(url_for('index'))

        app.logger.info(f"Found video file: {video_file_path}")

        # --- Extract Audio ---
        # Use shortcode and a unique ID for the output filename to avoid collisions
        # Output directly into the main DOWNLOAD_FOLDER
        final_audio_filename = f"{shortcode}_{request_id}.mp3"
        output_audio_path = os.path.join(
            app.config['DOWNLOAD_FOLDER'], final_audio_filename)

        app.logger.info(f"Starting audio extraction to: {output_audio_path}")
        success, message = extract_audio_ffmpeg(
            video_file_path, output_audio_path)

        if not success:
            flash(message, 'error')  # Use the error message from the function
            # Keep temp dir for debugging if ffmpeg failed
            # shutil.rmtree(temp_download_dir) # Optionally remove even on failure
            return redirect(url_for('index'))

        # If successful, redirect to the serving endpoint
        flash(f'Audio ready: {final_audio_filename}', 'success')
        return redirect(url_for('serve_file', filename=final_audio_filename))

    except instaloader.exceptions.InstaloaderException as e:
        app.logger.error(f"Instaloader error for {shortcode}: {e}")
        error_msg = f"Error interacting with Instagram: {e}"
        if "429" in str(e) or "Too many requests" in str(e):
            error_msg = "Rate limited by Instagram. Please try again later."
        elif "Private Profile" in str(e) or "login required" in str(e):
            error_msg = "Cannot download from private profiles or content requiring login."
        flash(error_msg, 'error')
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(
            f"An unexpected error occurred during download/extraction: {e}", exc_info=True)
        flash('An unexpected server error occurred. Please try again later.', 'error')
        return redirect(url_for('index'))
    finally:
        # --- Cleanup ---
        # Remove the temporary video download directory *unless* ffmpeg failed and we want to debug
        # Only remove temp if video was found and audio likely processed
        if video_file_path and final_audio_filename:
            try:
                app.logger.info(
                    f"Removing temporary directory: {temp_download_dir}")
                shutil.rmtree(temp_download_dir)
            except OSError as e:
                app.logger.warning(
                    f"Could not remove temporary directory {temp_download_dir}: {e}")
        elif os.path.exists(temp_download_dir):
            # Attempt cleanup even if intermediate steps failed but temp dir exists
            try:
                app.logger.info(
                    f"Cleaning up potentially incomplete temp directory: {temp_download_dir}")
                shutil.rmtree(temp_download_dir)
            except OSError as e:
                app.logger.warning(
                    f"Could not remove temp directory during cleanup: {e}")


@app.route('/serve/<filename>')
def serve_file(filename):
    """Serves the extracted audio file for download."""
    try:
        # Important: Ensure the filename is safe (basic check)
        if '..' in filename or filename.startswith('/'):
            abort(404)  # Prevent path traversal

        # Check if file exists before attempting to send
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if not os.path.isfile(file_path):
            app.logger.error(f"Requested file not found: {file_path}")
            abort(404)

        app.logger.info(f"Serving file: {filename}")
        # Use send_from_directory for security
        # as_attachment=True prompts the browser to download the file
        return send_from_directory(
            app.config['DOWNLOAD_FOLDER'],
            filename,
            as_attachment=True,
            # Common mimetype for .m4a (AAC in MP4 container)
            mimetype='audio/mp4'
        )
    except FileNotFoundError:
        app.logger.error(f"File not found exception for: {filename}")
        abort(404)
    except Exception as e:
        app.logger.error(f"Error serving file {filename}: {e}", exc_info=True)
        abort(500)  # Internal Server Error


if __name__ == '__main__':
    # Set host='0.0.0.0' to make it accessible on your network
    # debug=True is helpful during development but should be OFF in production
    app.run(host='0.0.0.0', port=5000, debug=True)
