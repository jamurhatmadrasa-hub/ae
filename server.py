"""AE Downloader Flask backend. Requires ffmpeg for audio conversion/merging."""
import ipaddress
import os
import shutil
import socket
import tempfile
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)
CORS(app, expose_headers=["Content-Disposition"])
HAS_ARIA = shutil.which("aria2c") is not None


def valid_public_url(value):
    """Reject non-HTTP(S), credentialed, local, and non-public destinations."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            return False
        try:
            addresses = [ipaddress.ip_address(host.split("%", 1)[0])]
        except ValueError:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)]
        return bool(addresses) and all(ip.is_global for ip in addresses)
    except (ValueError, OSError, IndexError):
        return False


def require_public_url(url):
    if not valid_public_url(url):
        return jsonify(error="একটি বৈধ পাবলিক http/https লিংক দিন"), 400
    return None


def base_opts():
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "concurrent_fragment_downloads": 4, "retries": 3, "fragment_retries": 3, "socket_timeout": 20, "max_filesize": 1024 * 1024 * 1024}
    if HAS_ARIA:
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = {"aria2c": ["-x8", "-s8", "-k1M", "--file-allocation=none"]}
    else:
        opts["http_chunk_size"] = 10485760
    return opts


def size_of(fmt):
    return fmt.get("filesize") or fmt.get("filesize_approx") or 0


@app.get("/api/info")
def api_info():
    url = (request.args.get("url") or "").strip()
    error = require_public_url(url)
    if error:
        return error
    try:
        with YoutubeDL({**base_opts(), "skip_download": True}) as ydl:
            data = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        return jsonify(error=str(exc).replace("ERROR: ", "")[:300]), 400
    except Exception as exc:
        app.logger.warning("Metadata extraction failed: %s", exc)
        return jsonify(error="ভিডিওর তথ্য পাওয়া যায়নি"), 400
    if data.get("entries"):
        data = next((entry for entry in data["entries"] if entry), data)
    formats = data.get("formats") or []
    duration = data.get("duration") or 0
    audio_formats = [f for f in formats if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")]
    best_audio = max(audio_formats, key=lambda f: (f.get("abr") or 0, size_of(f)), default=None)
    audio_size = size_of(best_audio) if best_audio else 0
    by_height = {}
    for fmt in formats:
        height = fmt.get("height")
        if not height or fmt.get("vcodec") in (None, "none"):
            continue
        size = size_of(fmt) + (0 if fmt.get("acodec") not in (None, "none") else audio_size)
        score = size_of(fmt) or (fmt.get("tbr") or 0) * 1000
        if height not in by_height or score > by_height[height]["score"]:
            by_height[height] = {"score": score, "size": size}
    video = [{"height": h, "label": f"{h}p", "note": "ভিডিও + অডিও", "size": by_height[h]["size"], "hd": h >= 720} for h in sorted(by_height, reverse=True)]
    estimate = lambda kbps: int(duration * kbps * 1000 / 8) if duration else 0
    audio = [{"label": f"MP3 • {rate} kbps", "fmt": "mp3", "abr": rate, "size": estimate(rate), "note": "অডিও"} for rate in (320, 192, 128)]
    audio.append({"label": "M4A • অরিজিনাল", "fmt": "m4a", "abr": 0, "size": audio_size or estimate(128), "note": "কনভার্ট ছাড়া"})
    return jsonify(title=data.get("title"), thumbnail=data.get("thumbnail"), uploader=data.get("uploader") or data.get("channel"), duration=duration, video=video, audio=audio)


@app.get("/api/download")
def api_download():
    url = (request.args.get("url") or "").strip()
    error = require_public_url(url)
    if error:
        return error
    kind = request.args.get("kind", "video")
    if kind not in ("video", "audio"):
        return jsonify(error="অবৈধ ডাউনলোড ধরন"), 400
    tmp = tempfile.mkdtemp(prefix="aedl_")
    opts = {**base_opts(), "outtmpl": os.path.join(tmp, "%(title).80B.%(ext)s")}
    if kind == "audio":
        fmt = request.args.get("fmt", "mp3")
        abr = request.args.get("abr", "192")
        if fmt == "m4a":
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        elif fmt == "mp3":
            try:
                quality = str(max(64, min(320, int(abr))))
            except ValueError:
                quality = "192"
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}]
        else:
            shutil.rmtree(tmp, ignore_errors=True)
            return jsonify(error="অবৈধ অডিও ফরম্যাট"), 400
    else:
        try:
            height = max(144, min(4320, int(request.args.get("height", "720"))))
        except ValueError:
            height = 720
        opts["format"] = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
        opts["merge_output_format"] = "mp4"
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        files = [os.path.join(tmp, name) for name in os.listdir(tmp) if not name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("ফাইল তৈরি হয়নি")
        path = max(files, key=os.path.getsize)
        response = send_file(path, as_attachment=True, download_name=os.path.basename(path))
        response.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
        return response
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        app.logger.warning("Download failed: %s", exc)
        return jsonify(error="ডাউনলোড ব্যর্থ হয়েছে; লিংক ও সার্ভার কনফিগারেশন পরীক্ষা করুন"), 400


@app.get("/")
def root():
    return send_from_directory(BASE, "AE-Downloader.html")


@app.get("/<path:name>")
def static_files(name):
    if name.startswith("api/"):
        return jsonify(error="not found"), 404
    return send_from_directory(BASE, name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
