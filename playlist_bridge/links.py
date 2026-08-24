"""Parse a pasted playlist link into (provider, playlist_id)."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

SPOTIFY = "spotify"
YTMUSIC = "ytmusic"


class LinkError(ValueError):
    pass


_SPOTIFY_URI = re.compile(r"^spotify:playlist:([A-Za-z0-9]+)$")
_SPOTIFY_PATH = re.compile(r"/playlist/([A-Za-z0-9]+)")


def parse_link(link: str) -> tuple[str, str]:
    """Return (provider, playlist_id). Raises LinkError if unrecognized."""
    link = link.strip()
    if not link:
        raise LinkError("Empty link.")

    m = _SPOTIFY_URI.match(link)
    if m:
        return SPOTIFY, m.group(1)

    parsed = urlparse(link if "://" in link else f"https://{link}")
    host = parsed.netloc.lower().removeprefix("www.")

    if "spotify.com" in host:
        m = _SPOTIFY_PATH.search(parsed.path)
        if not m:
            raise LinkError(f"Spotify link has no playlist id: {link}")
        return SPOTIFY, m.group(1)

    if "youtube.com" in host or "youtu.be" in host:
        qs = parse_qs(parsed.query)
        if "list" in qs and qs["list"]:
            return YTMUSIC, qs["list"][0]
        raise LinkError(
            f"YouTube link has no ?list= playlist id: {link}\n"
            "Open the playlist itself (not a single video) and copy that URL."
        )

    raise LinkError(
        f"Unrecognized link: {link}\n"
        "Expected an open.spotify.com or music.youtube.com playlist URL."
    )


def other_provider(provider: str) -> str:
    return YTMUSIC if provider == SPOTIFY else SPOTIFY
