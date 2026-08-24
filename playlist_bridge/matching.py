"""Title/artist normalization and fuzzy match scoring.

The hard part of playlist transfer is that the same song is titled
differently on each service. This module strips the noise then scores
candidates on title, artist, and duration.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .models import MatchResult, Track

# Parenthetical/bracketed junk that doesn't identify the song.
_NOISE_PATTERNS = [
    r"\((?:official\s+)?(?:music\s+)?video\)",
    r"\((?:official\s+)?audio\)",
    r"\(official(?:\s+\w+)*\)",
    r"\(lyrics?(?:\s+video)?\)",
    r"\(visuali[sz]er\)",
    r"\(remaster(?:ed)?(?:\s+\d{4})?\)",
    r"\(\d{4}\s+remaster(?:ed)?\)",
    r"\(deluxe(?:\s+\w+)*\)",
    r"\(bonus\s+track\)",
    r"\(explicit(?:\s+\w+)*\)",
    r"\(clean(?:\s+version)?\)",
    r"\(single\s+version\)",
    r"\(album\s+version\)",
    r"\(radio\s+edit\)",
    r"\(hd\)",
    r"\(4k\)",
]

# Same ideas but with square brackets.
_NOISE_PATTERNS += [p.replace(r"\(", r"\[").replace(r"\)", r"\]") for p in _NOISE_PATTERNS]

# Trailing " - Remastered 2011" style suffixes.
_DASH_NOISE = re.compile(
    r"\s+-\s+(?:"
    r"remaster(?:ed)?(?:\s+\d{4})?"
    r"|\d{4}\s+remaster(?:ed)?"
    r"|single\s+version|album\s+version|radio\s+edit"
    r"|official\s+(?:music\s+)?video|official\s+audio"
    r"|lyrics?(?:\s+video)?"
    r"|explicit|clean"
    r")\s*$",
    re.IGNORECASE,
)

_FEAT = re.compile(
    r"\s*[\(\[]?\s*\b(?:feat|ft|featuring|with)\b\.?\s+[^\)\]]*[\)\]]?",
    re.IGNORECASE,
)

_NOISE_RE = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]

# Artist suffixes YouTube appends.
_ARTIST_NOISE = re.compile(r"\s*-\s*topic\s*$|\s*vevo\s*$", re.IGNORECASE)


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_title(title: str, *, drop_feat: bool = True) -> str:
    """Reduce a track title to its comparable core."""
    out = title
    for pat in _NOISE_RE:
        out = pat.sub(" ", out)
    out = _DASH_NOISE.sub("", out)
    if drop_feat:
        out = _FEAT.sub(" ", out)
    return _flatten(out)


def normalize_artist(artist: str) -> str:
    return _flatten(_ARTIST_NOISE.sub("", artist))


def _flatten(text: str) -> str:
    """Lowercase, de-accent, strip punctuation, collapse whitespace."""
    out = strip_accents(text).lower()
    out = out.replace("&", " and ")
    out = re.sub(r"[^\w\s]", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def title_score(source: str, candidate: str) -> float:
    """Best of full-title and feat-stripped comparison."""
    return max(
        _ratio(normalize_title(source), normalize_title(candidate)),
        _ratio(
            normalize_title(source, drop_feat=False),
            normalize_title(candidate, drop_feat=False),
        ),
    )


def artist_score(source: list[str], candidate: list[str]) -> float:
    """Symmetric best-pair matching, tolerant of differing artist counts."""
    if not source or not candidate:
        return 0.0
    src = [normalize_artist(a) for a in source if a]
    cand = [normalize_artist(a) for a in candidate if a]
    if not src or not cand:
        return 0.0

    # Direct hit on the primary artist is the strongest signal.
    if src[0] and src[0] == cand[0]:
        return 1.0

    # Otherwise: how well does each source artist find a home in the candidate?
    per_artist = [max(_ratio(s, c) for c in cand) for s in src]
    best = max(per_artist)
    joined = _ratio(" ".join(src), " ".join(cand))
    return max(best, joined)


def duration_score(source_ms: int | None, cand_ms: int | None) -> float:
    """1.0 within 3s, tapering to 0.0 at 30s difference. Neutral if unknown."""
    if not source_ms or not cand_ms:
        return 0.5
    delta = abs(source_ms - cand_ms) / 1000.0
    if delta <= 3:
        return 1.0
    if delta >= 30:
        return 0.0
    return 1.0 - (delta - 3) / 27.0


# Weights: artist and title carry the decision, duration breaks ties.
W_TITLE, W_ARTIST, W_DURATION = 0.45, 0.40, 0.15


def score_candidate(source: Track, candidate: Track) -> float:
    """Combined 0..1 confidence that `candidate` is `source`."""
    if source.isrc and candidate.isrc and source.isrc == candidate.isrc:
        return 1.0

    t = title_score(source.title, candidate.title)
    a = artist_score(source.artists, candidate.artists)
    d = duration_score(source.duration_ms, candidate.duration_ms)

    score = W_TITLE * t + W_ARTIST * a + W_DURATION * d

    # A wildly different runtime almost always means wrong song
    # (live version, extended mix, hour-long loop), so cap it.
    if d == 0.0 and source.duration_ms and candidate.duration_ms:
        score = min(score, 0.55)

    return score


def pick_best(
    source: Track,
    candidates: list[Track],
    threshold: float = 0.62,
    keep: int = 3,
) -> MatchResult:
    """Score all candidates and return the best if it clears `threshold`."""
    if not candidates:
        return MatchResult(source=source, best=None, score=0.0, candidates=[])

    scored = sorted(
        ((c, score_candidate(source, c)) for c in candidates),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top, top_score = scored[0]
    best = top if top_score >= threshold else None
    return MatchResult(
        source=source,
        best=best,
        score=top_score,
        candidates=scored[:keep],
    )
