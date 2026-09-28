"""Dev-only stand-in for the gapgpt image API.

Exercising the studio normally costs credits and needs a real key. This little
server speaks just enough of the OpenAI image API for the studio to work end to
end: it answers ``POST /v1/images/generations`` with a URL, and serves that URL
as a real PNG built from the prompt (so different prompts visibly differ).

Usage — in one terminal:

    python scripts/mock_image_provider.py --port 8799

Then point the provider settings at it (Admin → AI provider settings, or):

    python manage.py shell -c "from imagegen.models import AIConfig; \\
        c = AIConfig.load(); c.base_url = 'http://127.0.0.1:8799/v1'; \\
        c.api_key = 'sk-mock'; c.save()"

Not for production: it has no auth, no rate limits and no persistence.
"""

import argparse
import hashlib
import io
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

_IMAGES = {}
SIZE = 512


def _render(prompt, seed):
    """A recognisable placeholder: gradient + rings + the prompt's hue."""
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    base_hue = digest[0] / 255
    rng = random.Random(seed)

    image = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(image)
    for y in range(SIZE):
        shade = y / SIZE
        draw.line(
            [(0, y), (SIZE, y)],
            fill=(
                int(40 + 90 * base_hue * (1 - shade)),
                int(30 + 70 * shade),
                int(120 + 90 * (1 - base_hue) * shade),
            ),
        )
    for _ in range(6):
        x0, x1 = sorted((rng.randint(-100, SIZE), rng.randint(0, SIZE + 100)))
        y0, y1 = sorted((rng.randint(-100, SIZE), rng.randint(0, SIZE + 100)))
        draw.ellipse([x0, y0, x1, y1], outline=(240, 240, 250), width=2)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "PromptyaMock/1.0"

    def log_message(self, fmt, *args):  # keep the console readable
        print("mock:", fmt % args)

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.endswith("/images/generations"):
            self._json(404, {"error": {"message": "not found"}})
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"error": {"message": "invalid json"}})
            return

        if not self.headers.get("Authorization", "").startswith("Bearer "):
            self._json(401, {"error": {"message": "missing api key"}})
            return

        if self.server.delay:
            time.sleep(self.server.delay)

        prompt = str(payload.get("prompt") or "")
        token = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]
        if token not in _IMAGES:
            _IMAGES[token] = _render(prompt, seed=int(token[:6], 16))

        host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
        self._json(200, {"data": [{"url": f"http://{host}/images/{token}.png"}]})

    def do_GET(self):
        if not self.path.startswith("/images/"):
            self._json(404, {"error": {"message": "not found"}})
            return
        token = self.path.rsplit("/", 1)[-1].removesuffix(".png")
        data = _IMAGES.get(token)
        if data is None:
            self._json(404, {"error": {"message": "unknown image"}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to stall each generation, to imitate a slow model.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.delay = args.delay
    print(f"Mock image provider on http://127.0.0.1:{args.port}/v1 (delay {args.delay}s)")
    server.serve_forever()


if __name__ == "__main__":
    main()
