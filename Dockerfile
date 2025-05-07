# Dockerfile

# Choose a Python base image. Using slim versions reduces size.
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
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the working directory
COPY . .

# Create the downloads directory expected by the app
# and change ownership to a non-root user for security
RUN mkdir -p downloads && chown -R nobody:nogroup downloads

# Environment variables for Flask
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PORT=10000

# Expose the port the app runs on
EXPOSE ${PORT}

# Switch to a non-root user for security
USER nobody

# Command to run the application using Gunicorn
# Binds to 0.0.0.0 to be accessible from outside the container
# app:app refers to the Flask application instance 'app' within the 'app.py' file
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app