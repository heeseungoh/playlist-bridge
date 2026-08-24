"""Spotify provider. Stdlib only: urllib for REST, http.server for the OAuth loopback.

Uses Authorization Code with PKCE, so only a Client ID is needed - no client
secret ever touches disk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ..models import Playlist, Track
from .base import AuthError, search_queries

API = "https://api.spotify.com/v1"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = PROJECT_ROOT / ".cache" / "spotify_token.json"


def load_env() -> dict[str, str]:
    """Minimal .env reader - avoids a python-dotenv dependency."""
    env: dict[str, str] = {}
    path = PROJECT_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_REDIRECT_URI"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot handler that captures ?code= from the redirect."""

    result: dict[str, str] = {}

    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.result = {k: v[0] for k, v in params.items()}
        ok = "code" in _CallbackHandler.result
        body = (
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            f"<h2>{'Authorized.' if ok else 'Authorization failed.'}</h2>"
            "<p>You can close this tab and return to the terminal.</p>"
            "</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass  # keep the console clean


class SpotifyProvider:
    name = "spotify"
    label = "Spotify"

    def __init__(self):
        env = load_env()
        self.client_id = env.get("SPOTIFY_CLIENT_ID", "")
        self.redirect_uri = env.get(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        )
        if not self.client_id:
            raise AuthError(
                "Missing SPOTIFY_CLIENT_ID.\n"
                "  1. Create a free app at https://developer.spotify.com/dashboard\n"
                f"  2. Add this redirect URI exactly: {self.redirect_uri}\n"
                "  3. Copy .env.example to .env and paste the Client ID in."
            )
        self._token: dict | None = None
        self._user_id: str | None = None

    # ---------- auth ----------

    def _load_cached_token(self) -> dict | None:
        if not TOKEN_PATH.exists():
            return None
        try:
            return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _save_token(self, token: dict) -> None:
        token["expires_at"] = time.time() + token.get("expires_in", 3600) - 60
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")
        self._token = token

    def _token_request(self, data: dict) -> dict:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise AuthError(f"Spotify token request failed ({exc.code}): {detail}") from exc

    def _authorize_interactive(self) -> dict:
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        state = secrets.token_urlsafe(16)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(SCOPES),
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
        url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

        parsed = urllib.parse.urlparse(self.redirect_uri)
        server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 8888),
                            _CallbackHandler)
        _CallbackHandler.result = {}

        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        print("\nOpening Spotify authorization in your browser...")
        print(f"If it doesn't open, paste this:\n{url}\n")
        webbrowser.open(url)

        thread.join(timeout=300)
        server.server_close()

        result = _CallbackHandler.result
        if not result:
            raise AuthError("Timed out waiting for Spotify authorization.")
        if "error" in result:
            raise AuthError(f"Spotify denied authorization: {result['error']}")
        if result.get("state") != state:
            raise AuthError("OAuth state mismatch - aborting for safety.")

        token = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": result["code"],
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": verifier,
            }
        )
        self._save_token(token)
        return token

    def _access_token(self) -> str:
        token = self._token or self._load_cached_token()

        if token and token.get("expires_at", 0) > time.time():
            self._token = token
            return token["access_token"]

        if token and token.get("refresh_token"):
            try:
                refreshed = self._token_request(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": token["refresh_token"],
                        "client_id": self.client_id,
                    }
                )
                refreshed.setdefault("refresh_token", token["refresh_token"])
                self._save_token(refreshed)
                return refreshed["access_token"]
            except AuthError:
                pass  # fall through to a fresh login

        return self._authorize_interactive()["access_token"]

    # ---------- http ----------

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 payload: dict | None = None, _retries: int = 3) -> dict:
        url = f"{API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._access_token()}")
        if data:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and _retries > 0:
                wait = int(exc.headers.get("Retry-After", "2")) + 1
                print(f"  rate limited, waiting {wait}s...")
                time.sleep(wait)
                return self._request(method, path, params=params, payload=payload,
                                     _retries=_retries - 1)
            if exc.code == 401 and _retries > 0:
                self._token = None
                TOKEN_PATH.unlink(missing_ok=True)
                return self._request(method, path, params=params, payload=payload,
                                     _retries=_retries - 1)
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"Spotify API {method} {path} failed ({exc.code}): {detail}") from exc

    # ---------- provider interface ----------

    @staticmethod
    def _to_track(item: dict) -> Track | None:
        if not item or not item.get("id"):
            return None
        return Track(
            id=item["id"],
            title=item.get("name", ""),
            artists=[a["name"] for a in item.get("artists", []) if a.get("name")],
            album=(item.get("album") or {}).get("name"),
            duration_ms=item.get("duration_ms"),
            isrc=(item.get("external_ids") or {}).get("isrc"),
        )

    def fetch_playlist(self, playlist_id: str) -> Playlist:
        meta = self._request("GET", f"/playlists/{playlist_id}",
                             params={"fields": "name,description"})
        tracks: list[Track] = []
        offset = 0
        while True:
            page = self._request(
                "GET",
                f"/playlists/{playlist_id}/tracks",
                params={"limit": 100, "offset": offset,
                        "additional_types": "track"},
            )
            for row in page.get("items", []):
                track = self._to_track(row.get("track") or {})
                if track:
                    tracks.append(track)
            if not page.get("next"):
                break
            offset += 100

        return Playlist(
            id=playlist_id,
            name=meta.get("name", "Untitled"),
            description=meta.get("description") or "",
            tracks=tracks,
        )

    def search_track(self, track: Track, limit: int = 5) -> list[Track]:
        found: dict[str, Track] = {}
        for query in search_queries(track):
            page = self._request("GET", "/search",
                                 params={"q": query, "type": "track", "limit": limit})
            for item in (page.get("tracks") or {}).get("items", []):
                candidate = self._to_track(item)
                if candidate:
                    found.setdefault(candidate.id, candidate)
            if len(found) >= limit:
                break
        return list(found.values())

    def _me(self) -> str:
        if self._user_id is None:
            self._user_id = self._request("GET", "/me")["id"]
        return self._user_id

    def create_playlist(self, name: str, description: str = "") -> str:
        created = self._request(
            "POST",
            f"/users/{self._me()}/playlists",
            payload={"name": name, "description": description, "public": False},
        )
        return created["id"]

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        for i in range(0, len(track_ids), 100):
            chunk = track_ids[i:i + 100]
            self._request(
                "POST",
                f"/playlists/{playlist_id}/tracks",
                payload={"uris": [f"spotify:track:{t}" for t in chunk]},
            )

    def playlist_url(self, playlist_id: str) -> str:
        return f"https://open.spotify.com/playlist/{playlist_id}"
