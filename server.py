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

def load_json(p, default):
    try: return json.loads(p.read_text('utf-8'))
    except Exception: return default

def save_json(p, data):
    try: p.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    except Exception as e: print("[!] save", p.name, e)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(ROOT), **kw)
    def _path(self): return unquote(urlparse(self.path).path)

    def _send(self, body, ctype, status=200):
        if isinstance(body, str): body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8', status)

    def do_GET(self):
        p = self._path()

        if p == '/book.pdf' or p == '/upload/book.pdf':
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
                        self.send_response(416); self.send_header('Content-Range', f'bytes */{file_size}'); self.end_headers(); return
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
                    f.seek(start); remaining = end - start + 1
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk: break
                        try: self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError): return
                        remaining -= len(chunk)
            except Exception as e: print("GET book error:", e)
            return

        if p == '/status':
            self._json({'exists': BOOK.exists(), 'size': BOOK.stat().st_size if BOOK.exists() else 0}); return
        if p == '/highlights': self._json(load_json(HL_FILE, {})); return
        if p == '/bookmarks': self._json(load_json(BM_FILE, [])); return

        # Serve static (index.html, manifest.json, sw.js, icon.svg, etc.)
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
                self._json({'ok': True}); print("[x] Deleted")
            except: self.send_response(500); self.end_headers()
            return
        if p == '/highlights':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length) if length else b'{}'
            try: save_json(HL_FILE, json.loads(data.decode('utf-8'))); self._json({'ok': True})
            except: self.send_response(500); self.end_headers()
            return
        if p == '/bookmarks':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length) if length else b'[]'
            try: save_json(BM_FILE, json.loads(data.decode('utf-8'))); self._json({'ok': True})
            except: self.send_response(500); self.end_headers()
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
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return '127.0.0.1'

lan_ip = get_lan_ip()
print("== Urdu Book Server ==")
print(f"   Local : http://localhost:{PORT}")
print(f"   LAN   : http://{lan_ip}:{PORT}")
print(f"   Upload: {BOOK}\n")

with socketserver.TCPServer(("", PORT), H) as s:
    try: s.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
