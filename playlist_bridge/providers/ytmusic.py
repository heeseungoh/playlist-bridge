"""YouTube Music provider, wrapping ytmusicapi.

Reading and searching work unauthenticated. Creating playlists needs browser
auth, which we set up on demand from copied request headers.
"""

from __future__ import annotations

from pathlib import Path

from ..models import Playlist, Track
from .base import AuthError, search_queries

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTH_PATH = PROJECT_ROOT / ".cache" / "browser.json"

SETUP_HELP = f"""YouTube Music needs browser auth to create playlists.

  1. Open https://music.youtube.com in Chrome or Edge, signed in.
  2. Open DevTools (F12) -> Network tab.
  3. Click anything on the page to generate requests.
  4. Find a POST request to a URL containing '/youtubei/v1/'.
  5. Right-click it -> Copy -> Copy request headers.
  6. Run:  python -m playlist_bridge auth-ytmusic

That writes {AUTH_PATH}, which is gitignored.
"""


class YTMusicProvider:
    name = "ytmusic"
    label = "YouTube Music"

    def __init__(self):
        from ytmusicapi import YTMusic

        self._YTMusic = YTMusic
        self._client = None
        self._authed_client = None

    @property
    def client(self):
        """Unauthenticated client - fine for reading public playlists and search."""
        if self._client is None:
            self._client = self._YTMusic()
        return self._client

    @property
    def authed(self):
        """Authenticated client - required for any write."""
        if self._authed_client is None:
            if not AUTH_PATH.exists():
                raise AuthError(SETUP_HELP)
            try:
                self._authed_client = self._YTMusic(str(AUTH_PATH))
            except Exception as exc:
                raise AuthError(
                    f"YouTube Music auth failed ({exc}).\n"
                    "Your saved headers may have expired.\n\n" + SETUP_HELP
                ) from exc
        return self._authed_client

    @staticmethod
    def setup_auth(headers_raw: str) -> Path:
        """Persist browser headers for later authenticated calls."""
        from ytmusicapi import setup

        AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        setup(filepath=str(AUTH_PATH), headers_raw=headers_raw)
        return AUTH_PATH

    # ---------- provider interface ----------

    @staticmethod
    def _to_track(item: dict) -> Track | None:
        video_id = item.get("videoId")
        if not video_id:
            return None  # unavailable/deleted entries have no id

        seconds = item.get("duration_seconds")
        artists = [
            a["name"]
            for a in (item.get("artists") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        album = item.get("album")
        return Track(
            id=video_id,
            title=item.get("title", ""),
            artists=artists,
            album=album.get("name") if isinstance(album, dict) else album,
            duration_ms=int(seconds) * 1000 if seconds else None,
        )

    def fetch_playlist(self, playlist_id: str) -> Playlist:
        # Private playlists need auth; fall back automatically.
        try:
            data = self.client.get_playlist(playlist_id, limit=None)
        except Exception:
            data = self.authed.get_playlist(playlist_id, limit=None)

        tracks = []
        for row in data.get("tracks", []):
            track = self._to_track(row)
            if track:
                tracks.append(track)

        return Playlist(
            id=playlist_id,
            name=data.get("title", "Untitled"),
            description=data.get("description") or "",
            tracks=tracks,
        )

    def search_track(self, track: Track, limit: int = 5) -> list[Track]:
        found: dict[str, Track] = {}
        for query in search_queries(track):
            try:
                results = self.client.search(query, filter="songs", limit=limit)
            except Exception:
                continue
            for item in results:
                candidate = self._to_track(item)
                if candidate:
                    found.setdefault(candidate.id, candidate)
            if len(found) >= limit:
                break
        return list(found.values())

    def create_playlist(self, name: str, description: str = "") -> str:
        result = self.authed.create_playlist(
            title=name,
            description=description or "",
            privacy_status="PRIVATE",
        )
        # Returns a str id on success, or a dict on error.
        if isinstance(result, dict):
            raise RuntimeError(f"YouTube Music rejected playlist creation: {result}")
        return result

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        for i in range(0, len(track_ids), 100):
            chunk = track_ids[i:i + 100]
            self.authed.add_playlist_items(playlist_id, videoIds=chunk, duplicates=False)

    def playlist_url(self, playlist_id: str) -> str:
        return f"https://music.youtube.com/playlist?list={playlist_id}"
