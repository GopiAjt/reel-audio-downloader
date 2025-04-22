# Dockerfile

# Choose a Python base image. Using slim versions reduces size.
# Be specific with the version for reproducibility.
FROM python:3.10-slim-bullseye

# Set environment variables to prevent interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Install ffmpeg and clean up apt cache in the same layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy just the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the working directory
COPY . .

# Create the downloads directory expected by the app
# and change ownership to a non-root user for security
RUN mkdir downloads && chown -R nobody:nogroup downloads

# Environment variables for Flask
# FLASK_APP is used by 'flask' command, but gunicorn needs 'app:app' directly
# Set FLASK_ENV to production (disables debug mode)
ENV FLASK_ENV=production

# --- IMPORTANT: Secret Key Handling ---
# Setting SECRET_KEY here is INSECURE as it's baked into the image.
# It's better to pass it at runtime using `docker run -e SECRET_KEY=...`
# Or use Docker secrets / other secrets management tools.
# ENV SECRET_KEY='your_hardcoded_secret_key_here' # <--- DO NOT DO THIS IN PRODUCTION
# We will rely on passing it during `docker run` instead.

# Expose the port the app runs on (Gunicorn default or specified in CMD)
EXPOSE 5000

# Switch to a non-root user for security
USER nobody

# Command to run the application using Gunicorn
# Binds to 0.0.0.0 to be accessible from outside the container
# app:app refers to the Flask application instance 'app' within the 'app.py' file
# Adjust --workers based on your server's resources (e.g., 2 * CPU cores + 1)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]

# --- Alternative CMD using Flask development server (NOT FOR PRODUCTION) ---
# ENV FLASK_APP=app.py
# CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]