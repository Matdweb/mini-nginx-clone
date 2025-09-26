#!/usr/bin/env python3
"""
backend/server.py
Simple Python backend that serves /api/events as JSON with ETag + gzip and short-cache.
"""
import os
import json
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'events.json')
PORT = int(os.environ.get('PORT', '5000'))

def read_data():
    with open(DATA_PATH, 'rb') as f:
        return f.read()

def compute_etag_bytes(b):
    return hashlib.sha1(b).hexdigest()

class BackendHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self):
        if self.path == '/api/events':
            raw = read_data()
            etag = compute_etag_bytes(raw)
            # headers
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'public, max-age=30')
            self.send_header('Vary', 'Accept-Encoding')
            # conditional GET
            inm = self.headers.get('If-None-Match')
            if inm == etag:
                self.send_response(304)
                self.end_headers()
                return
            accept = self.headers.get('Accept-Encoding', '')
            body = raw
            if 'gzip' in accept:
                gz = gzip.compress(body)
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(gz)))
                self.end_headers()
                self.wfile.write(gz)
            else:
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return

        if self.path == '/_status':
            body = ('{"status":"backend ok","time":"%s"}' % datetime.now(timezone.utc).isoformat()).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, "Not Found")

def run():
    server = ThreadingHTTPServer(('0.0.0.0', PORT), BackendHandler)
    print(f"Backend listening on {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == '__main__':
    run()
