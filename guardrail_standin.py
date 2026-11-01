"""Local stand-in for a guardrail service and a chat model. Stdlib only, listens on 127.0.0.1.

POST /beta/litellm_basic_guardrail_api answers like a Generic Guardrail API service: it requires the x-api-key header
to equal the key given on the command line (401 otherwise), returns action BLOCKED when any checked text contains the
word "confidential" and action NONE for everything else. POST /v1/chat/completions answers like an OpenAI-compatible
chat model with a fixed reply. Every request is appended to a JSON-lines log, with the key reported only as matches,
wrong or missing.

Usage: python guardrail_standin.py <port> <expected x-api-key> <log path>
"""

import itertools
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
EXPECTED_KEY = sys.argv[2]
LOG_PATH = sys.argv[3]
BLOCKED_WORD = "confidential"
_ids = itertools.count(1)
_log_lock = threading.Lock()


def _texts(body: dict) -> list:
    texts = body.get("texts")
    return [text for text in texts if isinstance(text, str)] if isinstance(texts, list) else []


class Handler(BaseHTTPRequestHandler):
    server_version = "guardrail-standin/1"

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _log(self, entry: dict) -> None:
        with _log_lock, open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write(json.dumps({"path": self.path, **entry}) + "\n")

    def _key_state(self) -> str:
        sent = self.headers.get("x-api-key")
        if sent is None:
            return "missing"
        return "matches" if sent == EXPECTED_KEY else "wrong"

    def do_GET(self) -> None:
        self._log({"method": "GET"})
        self._send(200 if self.path.rstrip("/") in ("", "/health") else 404, {})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        route = self.path.split("?", 1)[0].rstrip("/")
        if route == "/beta/litellm_basic_guardrail_api":
            self._guardrail(body)
            return
        if route == "/v1/chat/completions":
            self._chat(body)
            return
        self._log({"method": "POST", "unknown_route": True})
        self._send(404, {"error": f"no stand-in route for {self.path}"})

    def _guardrail(self, body: dict) -> None:
        key_state = self._key_state()
        texts = _texts(body)
        if key_state != "matches":
            self._log({"x_api_key": key_state, "texts": texts, "status": 401})
            self._send(401, {"error": f"x-api-key {key_state}"})
            return
        blocked = any(BLOCKED_WORD in text.lower() for text in texts)
        action = "BLOCKED" if blocked else "NONE"
        self._log({"x_api_key": key_state, "input_type": body.get("input_type"), "texts": texts, "action": action})
        if blocked:
            self._send(200, {"action": "BLOCKED", "blocked_reason": f"stand-in policy blocks the word '{BLOCKED_WORD}'"})
            return
        self._send(200, {"action": "NONE"})

    def _chat(self, body: dict) -> None:
        request_id = next(_ids)
        messages = body.get("messages") or []
        prompt_words = sum(len(str(m.get("content", "")).split()) for m in messages if isinstance(m, dict))
        self._log({"model": body.get("model"), "messages": len(messages)})
        self._send(
            200,
            {
                "id": f"chatcmpl-standin{request_id:04d}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", ""),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Stand-in reply from 127.0.0.1"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": prompt_words, "completion_tokens": 5, "total_tokens": prompt_words + 5},
            },
        )

    def log_message(self, format, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
