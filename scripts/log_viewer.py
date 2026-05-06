#!/usr/bin/env python3
"""Tiny SSE log viewer for KhanaBazaar dev. Tails .dev/logs/*.log over HTTP."""
from __future__ import annotations

import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / ".dev" / "logs"
HOST = "0.0.0.0"
PORT = int(os.environ.get("LOG_VIEWER_PORT", "8001"))
ALLOWED = {"backend.log", "celery.log", "frontend.log", "ngrok.log"}
TAIL_BYTES = 32 * 1024
PING_INTERVAL = 15.0

INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KB dev logs</title>
<style>
*{box-sizing:border-box}
body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#0b0f17;color:#cfe6ff;margin:0;font-size:14px}
header{position:sticky;top:0;background:#152033;padding:10px 14px;border-bottom:1px solid #243245;z-index:1}
.tabs{display:flex;gap:14px;flex-wrap:wrap}
.tabs a{color:#79c0ff;text-decoration:none;padding:4px 8px;border-radius:6px}
.tabs a.active{background:#1f7feb;color:#fff}
.controls{margin-top:8px;font-size:12px;color:#9bb}
.controls button{background:#243245;color:#cfe6ff;border:0;padding:4px 10px;border-radius:6px;cursor:pointer}
pre{padding:12px;white-space:pre-wrap;word-break:break-word;margin:0}
.line-otp{color:#ffd166;font-weight:bold}
</style></head><body>
<header>
<div class="tabs">
<a data-f="backend.log">backend</a>
<a data-f="celery.log">celery</a>
<a data-f="frontend.log">frontend</a>
<a data-f="ngrok.log">ngrok</a>
</div>
<div class="controls">
<label><input type="checkbox" id="follow" checked> follow</label>
<button id="clear">clear</button>
<span id="status"></span>
</div>
</header>
<pre id="out"></pre>
<script>
const params = new URLSearchParams(location.search);
const f = params.get('f') || 'backend.log';
const basePath = location.pathname.endsWith('/') ? location.pathname : location.pathname + '/';
document.querySelectorAll('.tabs a').forEach(a => {
  a.href = basePath + '?f=' + a.dataset.f;
  if (a.dataset.f === f) a.classList.add('active');
});
function streamUrl(name) {
  const u = new URL(basePath + 'stream', location.origin);
  u.searchParams.set('f', name);
  return u.toString();
}
const out = document.getElementById('out');
const status = document.getElementById('status');
const follow = document.getElementById('follow');
document.getElementById('clear').onclick = () => { out.textContent = ''; };
const otpRe = /otp|verification|code\\s*[:=]/i;
function append(text) {
  const div = document.createElement('span');
  if (otpRe.test(text)) div.className = 'line-otp';
  div.textContent = text + '\\n';
  out.appendChild(div);
  if (follow.checked) window.scrollTo(0, document.body.scrollHeight);
}
function connect() {
  status.textContent = ' connecting...';
  const es = new EventSource(streamUrl(f));
  es.onopen = () => { status.textContent = ' live'; };
  es.onmessage = (e) => append(e.data);
  es.onerror = () => { status.textContent = ' reconnecting...'; es.close(); setTimeout(connect, 2000); };
}
connect();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **kw):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/stream":
            qs = parse_qs(u.query)
            fname = qs.get("f", ["backend.log"])[0]
            if fname not in ALLOWED:
                self.send_error(400, "unknown log")
                return
            fpath = LOG_DIR / fname
            if not fpath.exists():
                self.send_error(404, "log file missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Content-Encoding", "identity")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self._stream(fpath)
            return
        self.send_error(404)

    def _stream(self, fpath: Path):
        try:
            with fpath.open("r", errors="replace") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - TAIL_BYTES))
                tail = f.read().splitlines()[-300:]
                for line in tail:
                    if not self._send_line(line):
                        return
                last_ping = time.time()
                while True:
                    line = f.readline()
                    if line:
                        if not self._send_line(line.rstrip("\n")):
                            return
                        last_ping = time.time()
                    else:
                        time.sleep(0.4)
                        if time.time() - last_ping > PING_INTERVAL:
                            try:
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError):
                                return
                            last_ping = time.time()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_line(self, line: str) -> bool:
        try:
            data = line.encode("utf-8", "replace").replace(b"\r", b"")
            self.wfile.write(b"data: " + data + b"\n\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"log_viewer listening on http://{HOST}:{PORT} (logs: {LOG_DIR})", file=sys.stderr, flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
