from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json, os, re, shutil, subprocess, uuid, urllib.parse

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
UPLOADS = ROOT / "uploads"
OUTPUT = ROOT / "output"
UPLOADS.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)
MAX_SIZE = 2 * 1024 * 1024 * 1024

def get_ffmpeg():
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg is not installed. Run run.bat again or install imageio-ffmpeg."
        ) from exc

def probe(path):
    ff = get_ffmpeg()
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace")
    s = (r.stderr or "") + "\n" + (r.stdout or "")
    dm = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", s)
    vm = re.search(r"Stream #\d+(?::\d+)?[^\n]*?Video:[^\n]*?(\d{2,5})x(\d{2,5})", s)
    duration = 0.0
    if dm:
        h, m, sec = dm.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(sec)
    width = height = 0
    if vm:
        width, height = map(int, vm.groups())
    if not duration and not width:
        raise RuntimeError((r.stderr or "Could not read the video.")[-2000:])
    return {"duration": duration, "width": width, "height": height}

def save_multipart(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length > MAX_SIZE:
        raise ValueError("File too large")
    ctype = handler.headers.get("Content-Type", "")
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', ctype)
    if not m:
        raise ValueError("Invalid multipart boundary")
    boundary = (m.group(1) or m.group(2)).encode()
    body = handler.rfile.read(length)
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition:" not in part:
            continue
        head, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        data = data.rstrip(b"\r\n-")
        fm = re.search(br'filename="([^"]+)"', head)
        if not fm:
            continue
        original = fm.group(1).decode("utf-8", "ignore")
        ext = Path(original).suffix.lower()
        if ext not in {".mp4",".mov",".mkv",".webm",".m4v",".avi"}:
            raise ValueError("Unsupported video format")
        name = f"{uuid.uuid4()}{ext}"
        path = UPLOADS / name
        path.write_bytes(data)
        return name, original, path
    raise ValueError("No video file found")

def max_dims(meta, aspect):
    sw, sh = meta["width"], meta["height"]
    if aspect == "9:16":
        h = (int(min(sh, sw * 16 / 9)) // 2) * 2
        w = (int(round(h * 9 / 16)) // 2) * 2
        return w, h, h
    if aspect == "16:9":
        w = (int(min(sw, sh * 16 / 9)) // 2) * 2
        h = (int(round(w * 9 / 16)) // 2) * 2
        return w, h, w
    side = (min(sw, sh) // 2) * 2
    return side, side, side

class Handler(BaseHTTPRequestHandler):
    def send_json(self, obj, code=200):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            try:
                ff = get_ffmpeg()
                return self.send_json({"ok": True, "version": "0.1.0", "ffmpeg": os.path.basename(ff)})
            except Exception as exc:
                return self.send_json({"ok": False, "version": "0.1.0", "error": str(exc)}, 503)
        if path.startswith("/media/"):
            name = Path(path).name
            p = OUTPUT / name
            if not p.exists():
                return self.send_error(404)
            data = p.read_bytes()
            range_header = self.headers.get("Range")
            start, end = 0, len(data) - 1
            if range_header and range_header.startswith("bytes="):
                try:
                    spec = range_header[6:].split(",", 1)[0]
                    a, b = spec.split("-", 1)
                    if a:
                        start = int(a)
                    if b:
                        end = int(b)
                    else:
                        end = min(start + 1024 * 1024 - 1, len(data) - 1)
                    start = max(0, min(start, len(data) - 1))
                    end = max(start, min(end, len(data) - 1))
                    chunk = data[start:end + 1]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(chunk)))
                    self.end_headers()
                    self.wfile.write(chunk)
                    return
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        target = PUBLIC / ("index.html" if path in ("", "/") else Path(path).name)
        if not target.exists():
            return self.send_error(404)
        data = target.read_bytes()
        ctype = "text/html; charset=utf-8" if target.suffix == ".html" else "image/x-icon" if target.suffix == ".ico" else "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            if self.path == "/api/upload":
                name, original, path = save_multipart(self)
                meta = probe(path)
                return self.send_json({"id": name, "name": original, **meta})
            if self.path == "/api/generate":
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                vid = Path(str(body.get("id", ""))).name
                src = UPLOADS / vid
                if not src.exists():
                    return self.send_json({"error": "Video not found."}, 404)
                ff = get_ffmpeg()
                meta = probe(src)
                count = max(1, min(int(body.get("count", 5)), 10))
                clip = min(max(int(body.get("length", 35)), 1), 90, max(meta["duration"], 1))
                aspect = str(body.get("aspect", "9:16"))
                quality = str(body.get("quality", "balanced")).lower()
                mw, mh, ml = max_dims(meta, aspect)
                req = str(body.get("resolution", "source")).lower().strip()
                if req in {"", "source", "max", "source max"}:
                    target = ml
                elif req.startswith("custom:"):
                    target = int(req.split(":", 1)[1])
                else:
                    target = int(req.rstrip("p")) 
                target = max(2, min(target, ml))
                target -= target % 2
                if aspect == "9:16":
                    out_h, out_w = target, max(2, (round(target * 9 / 16) // 2) * 2)
                elif aspect == "16:9":
                    out_w, out_h = target, max(2, (round(target * 9 / 16) // 2) * 2)
                else:
                    out_w = out_h = target
                want = 9/16 if aspect == "9:16" else 16/9 if aspect == "16:9" else 1
                ratio = meta["width"] / meta["height"] if meta["height"] else 1
                if ratio > want:
                    crop_h = meta["height"]; crop_w = int(round(crop_h * want))
                else:
                    crop_w = meta["width"]; crop_h = int(round(crop_w / want))
                crop_w = max(2, crop_w // 2 * 2); crop_h = max(2, crop_h // 2 * 2)
                cx = max((meta["width"] - crop_w) // 2, 0); cy = max((meta["height"] - crop_h) // 2, 0)
                preset, crf = ("superfast", "18") if quality == "high" else ("ultrafast", "20")
                vf = f"crop={crop_w}:{crop_h}:{cx}:{cy},scale={out_w}:{out_h}:flags=bicubic,setsar=1"
                maxstart = max(meta["duration"] - clip, 0)
                clips = []
                for i in range(count):
                    start = maxstart / 2 if count == 1 else maxstart * i / (count - 1)
                    out = f"{uuid.uuid4()}.mp4"
                    dest = OUTPUT / out
                    r = subprocess.run(
                        [ff, "-y", "-ss", str(start), "-i", str(src), "-t", str(clip),
                         "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
                         "-c:v", "libx264", "-preset", preset, "-crf", crf,
                         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                         "-movflags", "+faststart", str(dest)],
                        capture_output=True, text=True, errors="replace"
                    )
                    if r.returncode:
                        raise RuntimeError((r.stderr or "FFmpeg failed.")[-1500:])
                    clips.append({"id": out, "title": f"Candidate clip {i+1}", "start": start, "end": start+clip,
                                  "duration": clip, "width": out_w, "height": out_h,
                                  "resolution": f"{out_w}×{out_h}", "url": "/media/" + out})
                return self.send_json({"clips": clips, "mode": "candidate-windows",
                                       "source": {"width": meta["width"], "height": meta["height"]},
                                       "max_output": {"width": mw, "height": mh, "long_side": ml}})
            return self.send_json({"error": "Not found"}, 404)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)

    def log_message(self, *args):
        pass

print("CinderClip local MVP -> http://localhost:8787")
ThreadingHTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
