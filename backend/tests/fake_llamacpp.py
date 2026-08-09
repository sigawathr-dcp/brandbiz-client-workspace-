"""Minimal fake Ollama server (native /api/chat NDJSON) for local verification."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


FAKE_CHUNKS = ["Hello", " from", " the", " fake", " LLM", "!"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silence access log

    def do_GET(self):
        if self.path in ("/api/tags", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()

        for i, text in enumerate(FAKE_CHUNKS):
            is_last = i == len(FAKE_CHUNKS) - 1
            chunk: dict = {
                "model": "qwen2.5-14b-local",
                "message": {"role": "assistant", "content": text},
                "done": is_last,
            }
            if is_last:
                chunk["done_reason"] = "stop"
                chunk["prompt_eval_count"] = 12
                chunk["eval_count"] = len(FAKE_CHUNKS)
            line = (json.dumps(chunk) + "\n").encode()
            self.wfile.write(line)
            self.wfile.flush()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8088), Handler)
    print("fake ollama listening on :8088")
    server.serve_forever()
