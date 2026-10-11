"""Project middleware.

ApiCompatMiddleware keeps the JSON API and the mobile client working with the
session-auth architecture:

1. CSRF enforcement is skipped for /api/ requests.  These endpoints already
   rely on session authentication and same-site cookies; the mobile client
   authenticates with the session cookie directly.
2. ``@login_required`` redirects (302 -> /login/) are converted into
   ``401 {"error": "Authentication required."}`` JSON responses for /api/
   paths so API clients receive a proper unauthorized status instead of an
   HTML login page.

MediaRangeMiddleware serves /media/ files with HTTP Range support so the
browser can seek inside large audio and video files without downloading them
whole.  Django's static() helper streams the full file (200) and ignores
Range headers, which makes ``media.seekable`` empty and resets every seek to
0:00 until the entire clip has buffered.
"""
import os
import re

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse

API_PREFIX = "/api/"

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


class ApiCompatMiddleware:
    """Convert @login_required redirects to 401 JSON for API paths.

    CSRF enforcement is intentionally NOT disabled — the frontend sends
    X-CSRFToken from the csrftoken cookie, and the mobile client must do the same.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.path.startswith(API_PREFIX)
            and response.status_code == 302
            and str(response.headers.get("Location", "")).startswith(str(settings.LOGIN_URL))
        ):
            return JsonResponse({"error": "Authentication required."}, status=401)
        return response


class MediaRangeMiddleware:
    """206 Partial Content for Range requests on /media/ files.

    Only active when the runserver/development media helper is what would
    otherwise answer (i.e. always in DEBUG); in production a real web server
    (nginx, S3/CloudFront) handles ranges natively and this stays inert
    because /media/ is not served by Django there.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method != "GET" or not request.path.startswith(settings.MEDIA_URL):
            return response
        if response.status_code != 200 or not getattr(response, "streaming", False):
            return response

        range_header = request.headers.get("Range")
        if not range_header:
            response.headers.setdefault("Accept-Ranges", "bytes")
            return response

        match = _RANGE_RE.match(range_header)
        if not match:
            return response

        file = getattr(response, "file_to_stream", None)
        if file is None or not hasattr(file, "seek"):
            return response

        try:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            raw_start, raw_end = match.groups()
            if raw_start == "":
                # suffix range: last N bytes
                length = min(int(raw_end), size)
                start = size - length
                end = size - 1
            else:
                start = int(raw_start)
                end = min(int(raw_end), size - 1) if raw_end else size - 1
                if start > end:
                    return HttpResponse(status=416)
            length = end - start + 1
            if start >= size:
                return HttpResponse(status=416)
        except (OSError, ValueError):
            return response

        file.seek(start)
        partial = FileResponse(
            _read_range(file, length),
            content_type=response.headers.get("Content-Type", "application/octet-stream"),
            status=206,
        )
        partial.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        partial.headers["Content-Length"] = str(length)
        partial.headers["Accept-Ranges"] = "bytes"
        return partial


def _read_range(file, length, chunk_size=64 * 1024):
    """Yield exactly *length* bytes from the file's current position."""
    remaining = length
    try:
        while remaining > 0:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        file.close()
