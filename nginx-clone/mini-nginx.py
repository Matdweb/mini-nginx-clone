#!/usr/bin/env python3
"""
mini-nginx.py
Simple Python web server that:
- Serves static files from ./public
- Reverse-proxies paths starting with /api to backend host/port (env BACKEND_HOST/BACKEND_PORT)
- Implements Cache-Control, ETag, Last-Modified conditional GETs
- Gzip-compresses compressible responses when client supports gzip
Uses only Python standard library.
"""
import os
import io
import sys
import gzip
import hashlib
import http.client
import urllib.parse
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), 'public')
PORT = int(os.environ.get('PORT', '80'))
BACKEND_HOST = os.environ.get('BACKEND_HOST', 'backend')
BACKEND_PORT = int(os.environ.get('BACKEND_PORT', '5000'))

# Ensure mimetypes knows common types
mimetypes.init()

def is_compressible(mime):
    return mime.startswith('text/') or mime in ('application/javascript', 'application/json') or mime.endswith('+xml')

def generate_etag_bytes(data_bytes):
    return hashlib.sha1(data_bytes).hexdigest()

def read_file_bytes(path):
    with open(path, 'rb') as f:
        return f.read()

class MiniNginxHandler(BaseHTTPRequestHandler):
    server_version = "MiniNginx/0.1"

    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_HEAD(self):
        return self.do_GET(head_only=True)

    def do_GET(self, head_only=False):
        try:
            if self.path == '/_status':
                self._handle_status()
                return

            if self.path.startswith('/api'):
                return self._handle_proxy()

            # serve static file (strip leading '/')
            parsed = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(parsed.path.lstrip('/'))
            if not path:
                path = 'index.html'
            # Prevent path traversal
            normalized = os.path.normpath(path)
            if normalized.startswith('..'):
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return

            full_path = os.path.join(PUBLIC_DIR, normalized)
            if os.path.isdir(full_path):
                full_path = os.path.join(full_path, 'index.html')

            if not os.path.exists(full_path):
                # SPA fallback: serve index.html for unknown paths to allow client-side routing
                fallback = os.path.join(PUBLIC_DIR, 'index.html')
                if os.path.exists(fallback):
                    full_path = fallback
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                    return

            self._serve_static(full_path, head_only=head_only)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Server error: {e}")
            raise

    def _handle_status(self):
        body = ('{"status":"ok","time":"%s"}' % datetime.now(timezone.utc).isoformat()).encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_proxy(self):
        # Forward the request to backend using http.client
        try:
            conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=10)
            # preserve path + query
            path = self.path
            # build headers for backend request
            headers = {k: v for k, v in self.headers.items() if k.lower() != 'host'}
            headers['Host'] = BACKEND_HOST
            # read body if present
            body = None
            if 'content-length' in self.headers:
                length = int(self.headers['content-length'])
                body = self.rfile.read(length)
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            # copy status and headers
            self.send_response(resp.status, resp.reason)
            for key, val in resp.getheaders():
                if key.lower() == 'transfer-encoding':
                    continue
                if key.lower() == 'connection':
                    continue
                self.send_header(key, val)
            # Ensure Vary header present for compression differences
            self.send_header('Vary', 'Accept-Encoding')
            self.end_headers()
            # stream response
            chunk = resp.read(8192)
            while chunk:
                self.wfile.write(chunk)
                chunk = resp.read(8192)
            conn.close()
        except Exception as e:
            self.send_error(HTTPStatus.BAD_GATEWAY, f"Proxy error: {e}")

    def _serve_static(self, full_path, head_only=False):
        # read file bytes
        print(f'full path: ' + full_path)
        data = read_file_bytes(full_path)
        stat = os.stat(full_path)
        mime, _ = mimetypes.guess_type(full_path)
        mime = mime or 'application/octet-stream'
        # caching strategy
        if full_path.endswith('.html'):
            cache_control = 'no-cache'
        else:
            if any(full_path.endswith(ext) for ext in ('.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico')):
                cache_control = 'public, max-age=2592000'  # 30 days
            else:
                cache_control = 'public, max-age=3600'

        etag = generate_etag_bytes(data)
        last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # Set headers
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') or mime == 'application/json' else ''))
        self.send_header('Cache-Control', cache_control)
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', format_datetime(last_modified, usegmt=True))
        self.send_header('Vary', 'Accept-Encoding')

        # Handle conditional requests
        inm = self.headers.get('If-None-Match')
        ims = self.headers.get('If-Modified-Since')
        if inm == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.end_headers()
            return
        if ims:
            try:
                ims_dt = parsedate_to_datetime(ims)
                # compare (allowing equality)
                if ims_dt.tzinfo is None:
                    ims_dt = ims_dt.replace(tzinfo=timezone.utc)
                if ims_dt >= last_modified:
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.end_headers()
                    return
            except Exception:
                pass

        # HEAD only: finish headers without body
        accept_enc = self.headers.get('Accept-Encoding', '')
        should_gzip = 'gzip' in accept_enc and is_compressible(mime)
        body_bytes = data
        if should_gzip:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
                gz.write(body_bytes)
            body_bytes = buf.getvalue()
            self.send_header('Content-Encoding', 'gzip')

        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()

        if not head_only:
            self.wfile.write(body_bytes)


def run():
    print(f"Starting mini-nginx clone on port {PORT}, proxy -> {BACKEND_HOST}:{BACKEND_PORT}, serving {PUBLIC_DIR}")
    server = ThreadingHTTPServer(('0.0.0.0', PORT), MiniNginxHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        server.server_close()

if __name__ == '__main__':
    run()
