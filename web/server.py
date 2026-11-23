"""A small website for the agent. It listens on this computer only.

  /              talk to the agent from a browser
  /how           how it works, in diagrams
  /history       past calls
  /api/token     a short-lived pass into a new LiveKit room, with the agent invited
  /api/events    the call log as a live stream: recent calls, then each new line
                 the moment the agent writes it. Add ?call=<id> for one call.
  /api/articles  the six article titles, links and dates

The agent must be running (make serve). Standard library plus the LiveKit SDK.

Usage: uv run python web/server.py     then open http://localhost:8787
"""

import json
import os
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from livekit import api

from helpline.prompt import load_articles

HERE = Path(__file__).parent
LOG = HERE.parent / "logs" / "calls.jsonl"
AGENT_NAME = "helpline"
HOST = "127.0.0.1"  # transcripts are served without a login, so never beyond this machine
DEFAULT_PORT = 8787
CALLS_TO_REPLAY = 50  # a new visitor gets this many past calls, not the whole log
HEARTBEAT_SECONDS = 15  # a comment line now and then, so idle connections are not dropped
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/how": ("how.html", "text/html; charset=utf-8"),
    "/history": ("history.html", "text/html; charset=utf-8"),
    "/site.css": ("site.css", "text/css; charset=utf-8"),
    "/site.js": ("site.js", "text/javascript; charset=utf-8"),
}


def new_call() -> dict:
    """A pass that lets one browser join one new room, and asks LiveKit to send the agent."""
    room = f"web-{uuid.uuid4().hex[:8]}"
    token = (
        api.AccessToken()
        .with_identity(f"caller-{uuid.uuid4().hex[:6]}")
        .with_ttl(timedelta(minutes=10))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]))
        .to_jwt()
    )
    return {"url": os.environ["LIVEKIT_URL"], "token": token, "room": room}


def call_id_of(line: str) -> str | None:
    """The call a log line belongs to. None for a line that is not valid JSON."""
    try:
        return json.loads(line)["call_id"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def recent_calls(lines: list[str]) -> set[str]:
    newest_first = dict.fromkeys(call_id_of(line) for line in reversed(lines))
    return set(list(newest_first)[:CALLS_TO_REPLAY])


def follow_log(only: str | None) -> Iterator[str | None]:
    """Yield log lines for recent calls, then new lines as they are written, forever.
    Yields None when it is time for a heartbeat."""
    position, replaying, last_beat = 0, True, time.monotonic()
    while True:
        size = LOG.stat().st_size if LOG.exists() else 0
        if size < position:  # the log was cleared or replaced: start again
            position, replaying = 0, True
        if size > position:
            with LOG.open() as log:
                log.seek(position)
                lines = []
                while (line := log.readline()).endswith("\n"):  # leave a half-written line for later
                    position = log.tell()
                    lines.append(line.strip())
            wanted = {only} if only else recent_calls(lines) if replaying else None
            replaying = False
            for line in lines:
                call = call_id_of(line)
                if call and (wanted is None or call in wanted):
                    yield line
        elif time.monotonic() - last_beat > HEARTBEAT_SECONDS:
            last_beat = time.monotonic()
            yield None
        time.sleep(0.2)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path in FILES:
            name, kind = FILES[url.path]
            self._send((HERE / name).read_text(encoding="utf-8"), kind)
        elif url.path == "/api/events":
            self._stream(parse_qs(url.query).get("call", [None])[0])
        elif url.path == "/api/articles":
            articles = {
                a.id: {"title": a.title, "source": a.source, "updated": a.updated}
                for a in load_articles().values()
            }
            self._send(json.dumps(articles), "application/json")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/token":
            self.send_error(404)
        elif self._from_another_site():
            self.send_error(403)  # another website must not be able to start calls on our account
        else:
            self._send(json.dumps(new_call()), "application/json")

    def _from_another_site(self) -> bool:
        origin = self.headers.get("Origin")
        return bool(origin) and urlparse(origin).netloc != self.headers.get("Host")

    def _stream(self, only: str | None) -> None:
        """Server-sent events. The browser reconnects by itself if the line drops."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for line in follow_log(only):
                self.wfile.write(f"data: {line}\n\n".encode() if line else b": still here\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser tab closed

    def _send(self, body: str, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args) -> None:  # keep the terminal quiet
        pass


if __name__ == "__main__":
    load_dotenv(HERE.parent / ".env")
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    print(f"Open http://localhost:{port}")
    ThreadingHTTPServer((HOST, port), Handler).serve_forever()
