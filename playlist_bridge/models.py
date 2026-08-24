"""Provider-agnostic data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Track:
    """A single song, normalized across providers."""

    id: str
    title: str
    artists: list[str] = field(default_factory=list)
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None

    @property
    def artist_str(self) -> str:
        return ", ".join(self.artists)

    def __str__(self) -> str:
        return f"{self.artist_str} - {self.title}" if self.artists else self.title


@dataclass
class Playlist:
    id: str
    name: str
    tracks: list[Track] = field(default_factory=list)
    description: str | None = None

    def __len__(self) -> int:
        return len(self.tracks)


@dataclass
class MatchResult:
    """Outcome of searching for one source track on the destination provider."""

    source: Track
    best: Track | None
    score: float
    candidates: list[tuple[Track, float]] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.best is not None
