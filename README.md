# IRAD - Instagram Reel Audio Downloader

A web app to download audio from Instagram Reels with a beautiful dark/light theme.

![IRAD Screenshot](static/TRiSH%20square.png)

## Quick Start

### Local Development
```bash
# Clone and setup
git clone https://github.com/GopiAjt/reel-audio-downloader.git
cd reel-audio-downloader
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
flask run
```

### Docker
```bash
docker build -t reel-audio-downloader .
docker run -p 5000:5000 -e SECRET_KEY=your_secret_key reel-audio-downloader
```

## Features
- 🎵 Extract audio from Instagram Reels
- 🌓 Dark/light theme
- 📱 Responsive design
- 🔒 Secure file handling

## Tech Stack
- Flask
- Instaloader
- FFmpeg
- Bootstrap

Made with ❤️ by [GopiAjt](https://github.com/GopiAjt) 