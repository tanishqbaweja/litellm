from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/favicon.png", "/favicon-alt.png"):
            self.send_error(404)
            return
        image = (ROOT / self.path.removeprefix("/")).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(image)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(image)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 51477), Handler).serve_forever()
