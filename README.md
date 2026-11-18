# AE Downloader

বাংলা UI-সহ একটি installable Progressive Web App (PWA), সাথে yt-dlp ভিত্তিক Flask backend.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python server.py
```

Open <http://localhost:8000>. FFmpeg is recommended for MP3 extraction and merging separate video/audio streams. For best download speed, install `aria2c`.

## Deployment

Deploy the repository as a Python web service (the included `render.yaml` is configured for Render). The backend processes links submitted by users; deploy only with suitable outbound-network restrictions and resource limits. Do not expose it as an unrestricted public proxy.

The PWA requires HTTPS when hosted remotely. The service worker caches only the app shell; API responses and downloads are never cached.

## Use responsibly

Download only content you own or are authorized to download, and follow the source site's terms and applicable copyright law.
