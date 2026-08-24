"""Offline provider backed by a JSON fixture.

Spotify requires a registered developer app before you can read anything,
which is a hard stop if you can't create one. This provider stands in for a
real service so the rest of the pipeline - fetch, normalize, match, score,
report - can be exercised and verified end to end without credentials.

It is a development and testing aid, not a way to move real playlists.

Source usage:

    python -m playlist_bridge transfer offline:demo --to ytmusic --dry-run

Writes are captured in memory and printed rather than sent anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..matching import score_candidate
from ..models import Playlist, Track

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class OfflineProvider:
    name = "offline"
    label = "Offline fixture"

    def __init__(self, fixture: str = "spotify_demo"):
        self.fixture = fixture
        self._written: dict[str, list[str]] = {}

    # ---------- fixture loading ----------

    def _fixture_path(self, name: str) -> Path:
        # Accept a bare fixture name or a path to a JSON file.
        candidate = Path(name)
        if candidate.suffix == ".json" and candidate.exists():
            return candidate

        path = FIXTURES_DIR / f"{name}.json"
        if not path.exists():
            available = sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))
            raise FileNotFoundError(
                f"No fixture named '{name}'. Available: {', '.join(available) or 'none'}"
            )
        return path

    def _load(self, name: str) -> dict:
        return json.loads(self._fixture_path(name).read_text(encoding="utf-8"))

    @staticmethod
    def _to_track(row: dict) -> Track:
        return Track(
            id=row["id"],
            title=row.get("title", ""),
            artists=list(row.get("artists", [])),
            album=row.get("album"),
            duration_ms=row.get("duration_ms"),
            isrc=row.get("isrc"),
        )

    # ---------- provider interface ----------

    def fetch_playlist(self, playlist_id: str) -> Playlist:
        data = self._load(playlist_id or self.fixture)
        return Playlist(
            id=data.get("id", playlist_id),
            name=data.get("name", "Offline Playlist"),
            description=data.get("description", ""),
            tracks=[self._to_track(r) for r in data.get("tracks", [])],
        )

    def search_track(self, track: Track, limit: int = 5) -> list[Track]:
        """Search the fixture itself, so it can also serve as a destination."""
        pool = self.fetch_playlist(self.fixture).tracks
        scored = sorted(
            ((t, score_candidate(track, t)) for t in pool),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [t for t, _ in scored[:limit]]

    def create_playlist(self, name: str, description: str = "") -> str:
        playlist_id = f"offline-{len(self._written) + 1}"
        self._written[playlist_id] = []
        print(f"  [offline] would create playlist \"{name}\"")
        return playlist_id

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self._written.setdefault(playlist_id, []).extend(track_ids)
        print(f"  [offline] would add {len(track_ids)} track(s) to {playlist_id}")

    def playlist_url(self, playlist_id: str) -> str:
        return f"offline://{playlist_id}"

    @property
    def written(self) -> dict[str, list[str]]:
        """Tracks captured by add_tracks, for assertions in tests."""
        return self._written
