#!/usr/bin/env python3
import http.server, socketserver, os, json, re, socket
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = ROOT / "upload"
UPLOAD_DIR.mkdir(exist_ok=True)
BOOK = UPLOAD_DIR / "book.pdf"
HL_FILE = ROOT / "highlights.json"
BM_FILE = ROOT / "bookmarks.json"

ICON_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="100" fill="#e0e5ec"/><rect x="100" y="80" width="312" height="352" rx="20" fill="#5b6ef5"/><rect x="140" y="120" width="232" height="272" rx="10" fill="#fff"/><line x1="180" y1="180" x2="340" y2="180" stroke="#5b6ef5" stroke-width="10" stroke-linecap="round"/><line x1="180" y1="220" x2="340" y2="220" stroke="#5b6ef5" stroke-width="10" stroke-linecap="round"/><line x1="180" y1="260" x2="280" y2="260" stroke="#5b6ef5" stroke-width="10" stroke-linecap="round"/></svg>'''

MANIFEST_JSON = json.dumps({
    "name": "اردو کتاب — Reader",
    "short_name": "اردو کتاب",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#e0e5ec",
    "theme_color": "#e0e5ec",
    "icons": [
        {"src": "/icon.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any"},
        {"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any"},
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"}
    ]
}, ensure_ascii=False).encode('utf-8')

SW_JS = b'''const CACHE = "urdu-book-v3";
const SHELL = [
  "/", "/index.html", "/manifest.json", "/icon.svg",
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
  "https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;600&display=swap"
];
const API = ["/status","/highlights","/bookmarks","/upload","/delete"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL).catch(err => console.warn("cache fail", err))));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (API.includes(url.pathname)) return;
  if (url.pathname === "/book.pdf") {
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) caches.open(CACHE).then(c => c.put("/book.pdf", r.clone())).catch(()=>{});
      return r;
    }).catch(() => caches.match("/book.pdf")));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone())).catch(()=>{});
    return resp;
  }).catch(() => caches.match("/index.html"))));
});'''

def load_json(p, default):
    try: return json.loads(p.read_text('utf-8'))
    except Exception: return default

def save_json(p, data):
    try: p.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    except Exception as e: print("[!] save", p.name, e)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(ROOT), **kw)
    def _path(self): return unquote(urlparse(self.path).path)

    def _send(self, body, ctype, status=200, cache='no-store'):
        if isinstance(body, str): body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        if cache: self.send_header('Cache-Control', cache)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8', status)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def send_head(self):
        p = self._path()
        if p in ('/', '/index.html'):
            path = str(ROOT / 'index.html')
            if os.path.isfile(path):
                f = open(path, 'rb')
                fs = os.fstat(f.fileno())
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(fs.st_size))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.end_headers()
                return f
        return super().send_head()

    def do_HEAD(self):
        p = self._path()
        if p == '/book.pdf':
            if BOOK.exists():
                st = BOOK.stat()
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Length', str(st.st_size))
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
            else:
                self.send_response(404); self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self):
        p = self._path()
        if p == '/manifest.json': self._send(MANIFEST_JSON, 'application/manifest+json'); return
        if p == '/sw.js': self._send(SW_JS, 'application/javascript'); return
        if p == '/icon.svg': self._send(ICON_SVG, 'image/svg+xml'); return
        if p == '/book.pdf':
            if not BOOK.exists():
                self.send_response(404); self.end_headers(); return
            file_size = BOOK.stat().st_size
            range_header = self.headers.get('Range')
            start, end = 0, file_size - 1
            try:
                if range_header:
                    m = re.match(r'bytes=(\d+)-(\d*)', range_header)
                    if m:
                        start = int(m.group(1))
                        if m.group(2): end = int(m.group(2))
                    start = max(0, start); end = min(end, file_size - 1)
                    if start > end:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{file_size}')
                        self.end_headers(); return
                    self.send_response(206)
                    self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                    self.send_header('Content-Length', str(end - start + 1))
                else:
                    self.send_response(200)
                    self.send_header('Content-Length', str(file_size))
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                with open(BOOK, 'rb') as f:
                    f.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk: break
                        try: self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError): return
                        remaining -= len(chunk)
            except Exception as e:
                print("GET book error:", e)
            return
        if p == '/status':
            self._json({'exists': BOOK.exists(), 'size': BOOK.stat().st_size if BOOK.exists() else 0}); return
        if p == '/highlights': self._json(load_json(HL_FILE, {})); return
        if p == '/bookmarks': self._json(load_json(BM_FILE, [])); return
        super().do_GET()

    def do_POST(self):
        p = self._path()
        if p == '/upload':
            length = int(self.headers.get('Content-Length', 0))
            if length <= 0: self.send_response(400); self.end_headers(); return
            tmp = BOOK.with_suffix('.tmp')
            try:
                got = 0
                with open(tmp, 'wb') as f:
                    while got < length:
                        chunk = self.rfile.read(min(65536, length - got))
                        if not chunk: break
                        f.write(chunk); got += len(chunk)
                tmp.replace(BOOK)
                self._json({'ok': True, 'size': BOOK.stat().st_size})
                print(f"[+] Saved {got} bytes")
            except Exception as e:
                print("[!] Upload failed:", e)
                try: tmp.unlink(missing_ok=True)
                except: pass
                self.send_response(500); self.end_headers()
            return
        if p == '/delete':
            try:
                if BOOK.exists(): BOOK.unlink()
                self._json({'ok': True}); print("[x] Deleted book")
            except Exception as e:
                self.send_response(500); self.end_headers()
            return
        if p == '/highlights':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length) if length else b'{}'
            try:
                save_json(HL_FILE, json.loads(data.decode('utf-8')))
                self._json({'ok': True})
            except Exception as e: self.send_response(500); self.end_headers()
            return
        if p == '/bookmarks':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length) if length else b'[]'
            try:
                save_json(BM_FILE, json.loads(data.decode('utf-8')))
                self._json({'ok': True})
            except Exception as e: self.send_response(500); self.end_headers()
            return
        self.send_response(404); self.end_headers()

    def log_message(self, fmt, *args):
        msg = fmt % args
        if ' 206 ' in msg or ' 304 ' in msg: return
        print("[server]", msg)

PORT = int(os.environ.get('PORT', 8080))
socketserver.TCPServer.allow_reuse_address = True

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception: return '127.0.0.1'

lan_ip = get_lan_ip()
print("== Urdu Book Server ==")
print(f"   Local : http://localhost:{PORT}")
print(f"   LAN   : http://{lan_ip}:{PORT}  (same wifi -> laptop)")
print(f"   Upload: {BOOK}")
print()

with socketserver.TCPServer(("", PORT), H) as s:
    try: s.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
