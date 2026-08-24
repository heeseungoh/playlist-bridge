"""Shared provider interface."""

from __future__ import annotations

from typing import Protocol

from ..models import Playlist, Track


class Provider(Protocol):
    """What every music service must implement to participate in a transfer."""

    name: str
    label: str

    def fetch_playlist(self, playlist_id: str) -> Playlist:
        """Read a playlist and all of its tracks."""
        ...

    def search_track(self, track: Track, limit: int = 5) -> list[Track]:
        """Find candidate matches for a track from another service."""
        ...

    def create_playlist(self, name: str, description: str = "") -> str:
        """Create an empty playlist, returning its id."""
        ...

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Append tracks to an existing playlist."""
        ...

    def playlist_url(self, playlist_id: str) -> str:
        """Human-openable URL for a playlist."""
        ...


class AuthError(RuntimeError):
    """Raised when a provider isn't usable until the user does something."""


def search_queries(track: Track) -> list[str]:
    """Query strings to try, most specific first.

    Providers differ in how they tokenize, so we give the search a couple
    of shapes rather than betting everything on one string.
    """
    from ..matching import normalize_artist, normalize_title

    title = normalize_title(track.title)
    primary = normalize_artist(track.artists[0]) if track.artists else ""

    queries = []
    if primary:
        queries.append(f"{primary} {title}")
    queries.append(title)
    if len(track.artists) > 1:
        all_artists = " ".join(normalize_artist(a) for a in track.artists[:2])
        queries.append(f"{all_artists} {title}")

    seen, out = set(), []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out
