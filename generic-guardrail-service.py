import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EVENTS = Path(__file__).with_name("service-events.jsonl")
LOCK = threading.Lock()
KEYS = {
    "/beta/litellm_basic_guardrail_api": "qa-generic-local-key",
    "/updated/beta/litellm_basic_guardrail_api": "qa-generic-updated-key",
}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200 if self.path == "/health" else 404, {"status": "ok"})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        authorized = self.path in KEYS and self.headers.get("x-api-key") == KEYS[self.path]
        texts = payload.get("texts", [])
        event = {"path": self.path, "authorized": authorized, "input_type": payload.get("input_type"), "texts": texts}
        with LOCK, EVENTS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")
        if not authorized:
            self.reply(401, {"error": "The local fixture did not receive the configured API key"})
        elif any("qa-blocked-34927" in text for text in texts):
            self.reply(200, {"action": "BLOCKED", "blocked_reason": "Blocked by the local QA guardrail"})
        else:
            self.reply(200, {"action": "NONE", "texts": texts})

    def log_message(self, format, *args):
        print(format % args, flush=True)


if __name__ == "__main__":
    EVENTS.write_text("", encoding="utf-8")
    ThreadingHTTPServer(("127.0.0.1", 51476), Handler).serve_forever()
